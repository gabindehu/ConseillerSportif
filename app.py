from flask import Flask, render_template, request, jsonify
import requests
import math
import time
import subprocess
import re
import json
import os

app = Flask(__name__)

FILE_FACTS = "faits.lisp"

# Autocomplétion de la recherche des villes (API Gouv)
@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('q', '')
    if len(query) < 3: return jsonify([])
    try:
        r = requests.get("https://api-adresse.data.gouv.fr/search/", 
                         params={'q': query, 'limit': 10, 'type': 'municipality'})
        data = r.json()
        res = []
        for f in data.get('features', []):
            c = f['geometry']['coordinates']
            res.append({'label': f['properties']['label'], 'lon': c[0], 'lat': c[1]})
        return jsonify(res)
    except Exception as e:
        print(f"Error Autocomplete: {e}")
        return jsonify([])

# Reverse Geocoding (API Gouv)
@app.route('/reverse', methods=['GET'])
def reverse():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        print(f"DEBUG REVERSE: {lat}, {lon}")

        # On essaie d'abord l'API Gouv (France)
        r = requests.get("https://api-adresse.data.gouv.fr/reverse/", 
                         params={'lat': lat, 'lon': lon})
        data = r.json()
        
        if data.get('features'):
            props = data['features'][0]['properties']
            city = props.get('city') or props.get('label') or "Lieu inconnu"
            return jsonify({'city': city})
            
    except Exception as e:
        print(f"Erreur Reverse: {e}")
    
    # Si rien trouvé ou erreur on retourne une valeur par défaut
    return jsonify({'city': "Position GPS"})

# Calcul du dénivelé positif cumulé via Open-Elevation API
def get_elevation_gain(points):
    # Si pas assez de points, pas de dénivelé
    if not points or len(points) < 2:
        return 0

    # Échantillonnage des points pour limiter le nombre de requêtes
    step = max(1, len(points) // 50)  # On vise environ 50 points max par trajet
    sampled_points = points[::step]

    # Préparation des données des points pour l'API
    locations = [{"latitude": p["lat"], "longitude": p["lon"]} for p in sampled_points]

    try:
        # Appel API (Timeout court pour ne pas bloquer si l'API est lente)
        r = requests.post(
            "https://api.open-elevation.com/api/v1/lookup", 
            json={"locations": locations}, 
            timeout=5
        )
        data = r.json()
        
        # Calcul du dénivelé positif cumulé
        elevations = [float(res['elevation']) for res in data['results']]
        
        d_plus = 0
        for i in range(len(elevations) - 1):
            diff = elevations[i+1] - elevations[i]
            # On ne compte que si la différence est positive
            if diff > 0:
                d_plus += diff

        # On affiche le dénivelé calculé pour debug
        print(f"Dénivelé calculé: {d_plus} m sur {len(elevations)} points")       
        return int(d_plus)

    except Exception as e:
        print(f"Erreur API OpenElevation: {e}")
        # En cas d'erreur (timeout ou hors ligne), on retourne 0
        return 0

# Fonction utilitaire pour calculer la distance entre deux points GPS
def haversine(lat1, lon1, lat2, lon2):
    try:
        R = 6371  # Rayon Terre en km
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = math.sin(dLat/2) * math.sin(dLat/2) + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(dLon/2) * math.sin(dLon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c
    except:
        return 0

# Fonction de calcul de distance totale d'une liste de points 
def compute_distance(pts):
    dist = 0
    for i in range(len(pts) - 1):
        dist += haversine(
            pts[i]["lat"], pts[i]["lon"],
            pts[i+1]["lat"], pts[i+1]["lon"]
        )
    return dist

def fetch_and_save_routes(lat, lon, demo_mode=False):
    """ 
    Fonction principale pour récupérer les itinéraires autour d'une position GPS.
    Si demo_mode est True, on charge un fichier local de trajets à Compiègne.
    Sinon, on interroge l'API Overpass pour obtenir les itinéraires de randonnée et vélo autour de la position.
    """
    trajets = [] # Liste des trajets pour le site Web et pour construire fichier Lisp de la base de connaissances

    # MODE DÉMO À COMPIÈGNE QUI CHARGE UN FICHIER LOCAL
    if demo_mode:
        print("Mode chargement du fichier local de trajets à Compiègne")
        file = "trajets_compiegne.json"
        
        if os.path.exists(file):
            with open(file, "r", encoding="utf-8") as f:
                trajets = json.load(f)
        else:
            print(f"Erreur : Fichier {file} introuvable")

    # MODE NORMAL (Appel API Complexe)
    else:
        print(f"Recherche API Overpass autour de {lat}, {lon}")
        radius = 5000
        query = f"""
        [out:json][timeout:40];
        ( relation["route"~"hiking|bicycle"](around:{radius},{lat},{lon}); );
        out geom qt;
        """
        try:
            r = requests.get("http://overpass-api.de/api/interpreter", 
                           params={'data': query}, headers={'User-Agent': 'StudentProject/1.0'}, timeout=45)
            data = r.json()

        except Exception as e:
            print("Erreur API Overpass :", e)
            print(f"Code retour HTTP: {r.status_code}")
            data = {"elements": []}
            
        compteur_id = 1

        # Parcours des resultats de la requête API Overpass et extraction des itinéraires
        for el in data.get("elements", []): 
            # On limite à 30 itinéraires
            if len(trajets) >= 30:
                break

            tags = el.get("tags", {})
            name = tags.get("name", f"Itinéraire {compteur_id}")

            # Détermination du type d'activité (marche ou vélo)
            type_act = "velo" if "bicycle" in tags.get("route", "") else "marche"

            coords = []
            flat_points = []

            # Extraction des points
            for member in el.get("members", []):
                seg = member.get("geometry")
                if not seg:
                    continue

                segment = []

                for p in seg:
                    point = {
                        "lat": p["lat"],
                        "lon": p["lon"],
                    }
                    segment.append(point)

                coords.append(segment)
                flat_points.extend(segment)

            if len(flat_points) < 2:
                continue

            # Calcul de la distance totale
            dist_km = compute_distance(flat_points)

            # Filtrage simple des distances (on évite trop court ou trop long)
            if not (0.5 < dist_km < 90):
                continue

            # Calcul du dénivelé positif cumulé
            denivele = get_elevation_gain(flat_points)

            # Estimation de la difficulté (simple mais affinée lors de l'inférence par le système expert)
            diff = "moyenne"
            if type_act == "marche":
                if dist_km < 8 and denivele < 300: diff = "facile"
                elif dist_km > 20 or denivele > 800: diff = "difficile"
            else:
                if dist_km < 20 and denivele < 200: diff = "facile"
                elif dist_km > 60 or denivele > 1000: diff = "difficile"

            trajets.append({
                "id": compteur_id,
                "name": name,
                "km": round(dist_km, 1),
                "denivele": denivele,
                "type": type_act,
                "diff": diff,
                "segments": coords
            })

            compteur_id += 1
            time.sleep(0.1)  # Délai pour API OpenElevation

    # PARTIE COMMUNE AUX DEUX MODES

    # On génère la base de connaissances pour le système expert
    generate_lisp_database(trajets)
    
    # On renvoie les routes au site web
    print(f"Terminé : {len(trajets)} itinéraires prêts.")
    return trajets

def get_current_temperature(lat, lon):
    try:
        # On demande la météo courante pour les coordonnées données
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true"
        }
        r = requests.get(url, params=params, timeout=6)
        data = r.json()
        
        # On retourne la température (float)
        return data['current_weather']['temperature']
    except Exception as e:
        print(f"Erreur récupération température: {e}")
        return 10.0 # Valeur par défaut "tempérée" si l'API échoue

def generate_lisp_database(routes_list):
    """
    Génère un fichier itineraires.lisp définissant une variable globale *base-itineraires*
    Structure de rows attendue : [ID, Nom, Activite, Difficulte, Terrain, Distance, Denivele]
    """
    lisp_file = "itineraires.lisp"
    try:
        with open(lisp_file, 'w', encoding='utf-8') as f:
            f.write("(defparameter *base-itineraires* '(\n")
            
            for route in routes_list:
                # Récupération par Clés (= ids)
                id_itin = route['id']
                nom = route['name'].replace('"', '\\"')
                activite = route['type']      # 'velo' ou 'marche'
                difficulte = route['diff']    # 'facile', 'difficile'...
                distance = route['km']
                denivele = route['denivele']
                
                # Le terrain n'est pas stocké dans l'objet, on met une valeur par défaut
                terrain = route.get('terrain', 'mixte') 

                # Écriture dans le fichier Lisp par ligne
                line = f'    ({id_itin} "{nom}" {activite} {difficulte} {terrain} {distance} {denivele})\n'
                f.write(line)
            
            f.write("))\n")
        print(f"Base de données Lisp générée : {lisp_file}")
    except Exception as e:
        print(f"Erreur lors de la génération Lisp : {e}")

def generate_lisp_facts(d):
    try:
        with open(FILE_FACTS, 'w', encoding='utf-8') as f:
            f.write("(defparameter *faits-utilisateur* (list\n")
            
            # Liste des champs de type Booléen, si absent on considère 'faux'
            bool_fields = {
                'fatigue': 'etat_fatigue',
                'eau': 'eau',
                'equipement': 'equipement_adapte'
            }
            
            # Liste des champs Symboliques / Numérique, si absent car par d'envoi de l'html on garde 'nil'
            other_fields = {
                'activite': 'activite',
                'niveau': 'niveau_utilisateur',
                'distance': 'objectif_distance',
                'meteo': 'meteo',
                'vent': 'vent',
                'douleur': 'douleur',
                'temperature': 'temperature'
            }

            # Traitement des booléens 
            for k_py, k_lisp in bool_fields.items():
                val = d.get(k_py, 'false') 
                # On convertit en string minuscule pour uniformiser
                val_str = str(val).lower()
                
                # On ajoute 'vrai' à la liste des valeurs acceptées
                if val_str in ['true', 'on', 'vrai', '1']: 
                    val = 'vrai'
                else: 
                    val = 'faux'
                f.write(f"    '({k_lisp} {val})\n")

            # Traitement des autres champs
            for k_py, k_lisp in other_fields.items():
                val = d.get(k_py, 'nil') # Valeur par défaut 'nil' si clé absente
                # Pas de conversion vrai/faux ici, on garde la valeur brute (ex: 'pluie', 'velo')
                # Sauf si c'est numérique, on s'assure que c'est propre
                f.write(f"    '({k_lisp} {val})\n")

            f.write("))\n")
    except Exception as e:
        print(f"Erreur génération faits: {e}")

# Route pour exécuter le système expert Lisp : chaînage avant ou arrière
@app.route('/run-expert', methods=['POST'])
def run_expert():
    mode = request.json.get('mode', 'avant') # 'avant' ou 'arriere'
    
    # On s'assure que les fichiers faits.lisp et itineraires.lisp sont bien là (normalement générés par /submit juste avant)
    command = ["sbcl", "--script", mode+".lisp"]

    try:
        # Exécution de la commande Lisp
        print(f"Exécution de : {' '.join(command)}")
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=10 # Sécurité pour ne pas bloquer indéfiniment
        )
        
        output_logs = result.stdout
        error_logs = result.stderr

        # On cherche les IDs validés par le moteur d'inférence dans les logs pour les renvoyer au front pour afficher la liste des recommandations
        # On cherche le pattern : "Itinéraire X (...) ... VALIDÉ"
        recommended_ids = []
        for line in output_logs.splitlines():
            if "VALIDÉ" in line:
                # Regex pour trouver le nombre après "Itinéraire"
                match = re.search(r"Itinéraire\s+(\d+)", line)
                if match:
                    recommended_ids.append(int(match.group(1)))

        return jsonify({
            "success": True,
            "logs": output_logs,
            "errors": error_logs,
            "recommended_ids": recommended_ids
        })

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "logs": "Timeout: Le système expert a été trop long.", "recommended_ids": []})
    except Exception as e:
        print(f"Erreur Lisp: {e}")
        return jsonify({"success": False, "logs": f"Erreur système: {str(e)}", "recommended_ids": []})

@app.route('/')
def index(): return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    try:
        # Récupération des données JSON envoyées par le formulaire (données utilisateur et coordonnées GPS)
        data = request.json
        
        # Récupération du flag de mode démo (mode à compiègne uniquement)
        is_demo = data.get('demo_mode', False)

        # Récupération des coordonnées (ou coordonnées de Compiègne en mode démo)
        if is_demo:
            lat = 49.405934
            lon = 2.844366
        else:
            lat = float(data['lat'])
            lon = float(data['lon'])

        # Récupération de la température actuelle
        temp = get_current_temperature(lat, lon)
        data['temperature'] = temp

        # Affichage des données reçues
        print(data)

        # Génération des faits Lisp
        generate_lisp_facts(data)

        # Récupération et sauvegarde des itinéraires
        routes = fetch_and_save_routes(lat, lon, demo_mode=is_demo)

        return jsonify({"success": True, "nb_routes": len(routes), "routes": routes})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
