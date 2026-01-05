from flask import Flask, render_template, request, jsonify
import requests
import csv
import math
import time
import subprocess
import re

app = Flask(__name__)

FILE_ROUTES = "itineraires.csv"
FILE_FACTS = "faits.lisp"

# --- Mathématiques ---
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

# --- 1. Autocomplete (API Gouv) ---
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

# --- Reverse GPS (Bouton : Ma Localisation) ---
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
    
    # Fallback si rien trouvé ou erreur
    return jsonify({'city': "Position GPS"})

# --- Dénivelé (API OpenElevation) ---
def get_elevation_gain(points):
    # Si pas assez de points, pas de dénivelé
    if not points or len(points) < 2:
        return 0

    # 1. ÉCHANTILLONNAGE : On ne prend qu'un point tous les 10 ou 20 mètres environ
    # pour ne pas envoyer 2000 points à l'API (ce qui serait lent et pourrait bloquer)
    # On garde le premier et le dernier point, et un peu au milieu.
    step = max(1, len(points) // 50)  # On vise environ 50 points max par trajet
    sampled_points = points[::step]

    # 2. Préparation du payload pour l'API Open-Elevation
    # L'API attend: {"locations": [{"latitude": 10, "longitude": 10}, ...]}
    locations = [{"latitude": p["lat"], "longitude": p["lon"]} for p in sampled_points]

    try:
        # 3. Appel API (Timeout court pour ne pas bloquer l'app si l'API est lente)
        r = requests.post(
            "https://api.open-elevation.com/api/v1/lookup", 
            json={"locations": locations}, 
            timeout=5
        )
        data = r.json()
        
        # 4. Calcul du dénivelé positif cumulé
        elevations = [float(res['elevation']) for res in data['results']]
        
        d_plus = 0
        for i in range(len(elevations) - 1):
            diff = elevations[i+1] - elevations[i]
            # On ne compte que si ça monte
            if diff > 0:
                d_plus += diff

        print(f"Dénivelé calculé: {d_plus} m sur {len(elevations)} points")       
        return int(d_plus)

    except Exception as e:
        print(f"Erreur API OpenElevation: {e}")
        # En cas d'erreur (timeout ou hors ligne), on retourne 0
        return 0


# --- Récupération Routes ---
def fetch_and_save_routes(lat, lon):
    radius = 5000
    print(f"Recherche Overpass autour de {lat}, {lon}")

    query = f"""
    [out:json][timeout:25];
    (
      relation["route"~"hiking|bicycle"](around:{radius},{lat},{lon});
    );
    out geom qt;

    node(w) -> .nodes;
    .nodes out tags;
    """

    try:
        r = requests.get(
            "http://overpass-api.de/api/interpreter",
            params={'data': query},
            headers={'User-Agent': 'StudentProject/1.0'},
            timeout=20
        )
        r.raise_for_status()
        data = r.json()

    except Exception as e:
        print("Erreur Overpass:", e)
        return []

    frontend_routes = []
    csv_rows = []
    compteur_id = 1

    # --- petites fonctions internes simples ---
    def compute_distance(pts):
        dist = 0
        for i in range(len(pts) - 1):
            dist += haversine(
                pts[i]["lat"], pts[i]["lon"],
                pts[i+1]["lat"], pts[i+1]["lon"]
            )
        return dist

    # --- parcours des relations ---
    for el in data.get("elements", []): 
        tags = el.get("tags", {})
        name = tags.get("name", f"Itinéraire {compteur_id}")
        type_act = "velo" if "bicycle" in tags.get("route", "") else "marche"

        coords = []
        flat_points = []

        # Extraction points
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

                # ALTITUDE SI DISPONIBLE
                if "ele" in p:
                    point["ele"] = p["ele"]

                segment.append(point)

            coords.append(segment)
            flat_points.extend(segment)

        if len(flat_points) < 2:
            continue

        dist_km = compute_distance(flat_points)

        # Filtrage simple
        if not (0.5 < dist_km < 90):
            continue

        # Limite nombre de routes
        if len(frontend_routes) >= 30:
            break

        # Dénivelé (simple & optimisé)
        denivele = get_elevation_gain(flat_points)

        # Difficulté simplifiée
        diff = "moyenne"
        if type_act == "marche":
            if dist_km < 8 and denivele < 300: diff = "facile"
            elif dist_km > 20 or denivele > 800: diff = "difficile"
        else:
            if dist_km < 20 and denivele < 200: diff = "facile"
            elif dist_km > 60 or denivele > 1000: diff = "difficile"

        csv_rows.append([compteur_id, name, type_act, diff, "mixte", round(dist_km, 2), denivele])

        frontend_routes.append({
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
    
    print(f"Total itinéraires trouvés: {len(frontend_routes)}")

    # Sauvegarde CSV 
    #with open(FILE_ROUTES, "w", newline="", encoding="utf-8") as f:
    #    w = csv.writer(f, delimiter=';')
    #    w.writerow(["ID", "Nom", "Activite", "Difficulte", "Terrain", "Distance", "Denivele"])
    #    w.writerows(csv_rows)
    #print("Itinéraires sauvegardés dans", FILE_ROUTES)

    # Sauvegarde BD Lisp
    generate_lisp_database(csv_rows)

    return frontend_routes

def get_current_temperature(lat, lon):
    try:
        # On demande juste la météo courante
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true"
        }
        r = requests.get(url, params=params, timeout=3)
        data = r.json()
        
        # On retourne la température (float)
        return data['current_weather']['temperature']
    except Exception as e:
        print(f"Erreur récupération température: {e}")
        return 20.0 # Valeur par défaut "tempérée" si l'API échoue

def generate_lisp_database(rows):
    """
    Génère un fichier itineraires.lisp définissant une variable globale *base-itineraires*
    Structure de rows attendue : [ID, Nom, Activite, Difficulte, Terrain, Distance, Denivele]
    """
    lisp_file = "itineraires.lisp"
    try:
        with open(lisp_file, 'w', encoding='utf-8') as f:
            # On déclare une variable globale (defparameter ...)
            f.write("(defparameter *base-itineraires* '(\n")
            
            for row in rows:
                # Récupération des champs (selon votre structure CSV)
                # row = [ID, Nom, Activite, Difficulte, Terrain, Distance, Denivele]
                id_itin = row[0]
                nom = row[1].replace('"', '\\"') # Échapper les guillemets dans les noms
                activite = row[2].lower()         # Symbole (ex: velo)
                difficulte = row[3].lower()       # Symbole (ex: difficile)
                terrain = row[4].lower()          # Symbole (ex: mixte)
                distance = row[5]                 # Nombre
                denivele = row[6]                 # Nombre

                # Écriture de la ligne au format liste Lisp
                # Ex: (1 "Balade en forêt" velo facile terre 12.5 50)
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
            
            # 1. Liste des champs de type Booléen : Si absent du dictionnaire -> On veut 'faux'
            bool_fields = {
                'fatigue': 'etat_fatigue',
                'eau': 'eau',
                'equipement': 'equipement_adapte'
            }
            
            # 2. Liste des champs Symboliques / Numérique : si absent car par d'envoi de l'html -> On garde 'nil'
            other_fields = {
                'activite': 'activite',
                'niveau': 'niveau_utilisateur',
                'distance': 'objectif_distance',
                'meteo': 'meteo',
                'vent': 'vent',
                'douleur': 'douleur',
                'temperature': 'temperature'
            }

            # Traitement des booléens (Gestion du "non coché" = faux)
            for k_py, k_lisp in bool_fields.items():
                val = d.get(k_py, 'false') 
                # On convertit en string et minuscule pour être sûr
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

# --- Exécution du Système Expert ---
@app.route('/run-expert', methods=['POST'])
def run_expert():
    mode = request.json.get('mode', 'avant') # 'avant' ou 'arriere'
    
    # On s'assure que les fichiers faits.lisp et itineraires.lisp sont bien là 
    # (normalement générés par /submit juste avant)

    command = ["sbcl", "--script", mode+".lisp"]
    
    # Si plus tard vous faites un fichier différent pour le chaînage arrière :
    # if mode == 'arriere': command = ["sbcl", "--script", "chainage_arriere.lisp"]

    try:
        # 1. Exécution de la commande Lisp
        print(f"Exécution de : {' '.join(command)}")
        result = subprocess.run(
            command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            timeout=10 # Sécurité pour ne pas bloquer si boucle infinie
        )
        
        output_logs = result.stdout
        error_logs = result.stderr

        # 2. Parsing des résultats (On cherche les IDs VALIDÉ dans les logs)
        # On cherche le pattern : "Itinéraire X (...) ... VALIDÉ"
        # Adaptez la regex si votre message de sortie change dans le Lisp
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
        data = request.json
        lat = float(data['lat'])
        lon = float(data['lon'])
        temp = get_current_temperature(lat, lon)
        data['temperature'] = temp
        print(data)
        generate_lisp_facts(data)
        routes = fetch_and_save_routes(lat, lon)
        return jsonify({"success": True, "nb_routes": len(routes), "routes": routes})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
