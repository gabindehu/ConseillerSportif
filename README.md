# IA01 - Système Expert de Conseiller Sportif Intelligent

Ce projet est une application web couplant une interface (Python/Flask + Frontend) avec un **Système Expert d'ordre 0+** développé en Common Lisp (SBCL).

Il permet de récupérer des itinéraires réels récupérés par l'API OpenStreetMap autour de l'utilisateur et de filtrer ceux qui sont adaptés à sa condition physique, son niveau et la météo actuelle grâce au moteur d'inférence.

## Avertissement : APIs Gratuites

L'application utilise des services gratuits pour récupérer les trajets (Overpass API) le dénivelé (Open-Elevation) et la température (Open-Meteo).

Ces peuvent êtres instables donc si la recherche d'itinéraires tourne indéfiniment ou ne renvoie rien veuillez rafraîchir la page, réessayez et vérifiez votre connexion internet.

## Prérequis

Pour pouvoir lancer le projet, il faut avoir installé :

1.  **Python** (3.0 ou plus récent)
2.  **SBCL (Steel Bank Common Lisp)** : Le moteur Lisp est exécuté via ligne de commande par le serveur python.
      * *Linux :* `sudo apt install sbcl`
      * *Windows :* Télécharger et installer depuis [sbcl.org](https://www.sbcl.org/platform-table.html).
      * *MacOS :* `brew install sbcl`

## Installation

1.  Clonez ou extraire le dossier du projet.
2.  Installez les dépendances Python nécessaires (Flask : Utilisé pour créer le serveur web / Requests : Utilisé pour appeler les API externes) :

```bash
pip install flask requests
```

3.  Vérifiez que les fichiers suivants sont présents dans le dossier :
      * `app.py` (Serveur Web Flask)
      * `baseDeRegles.lisp` (La base de règles et des fonctions de service)
      * `avant.lisp` (Le moteur d'inférence de chaînage avant)
      * `arriere.lisp` (Le moteur d'inférence de chaînage arrière)
      * `templates/index.html` (L'interface utilisateur)

## Lancement

1.  Ouvrez un terminal dans le dossier du projet.
2.  Lancez le serveur Flask :

```bash
python app.py
```

3.  Ouvrez votre navigateur à l'adresse indiquée (généralement) :
      * `http://127.0.0.1:5000`

## Guide d'Utilisation


1.  **Localisation :** Entrez une ville ou utilisez le bouton "Ma Position" (GPS).
2.  **Profil :** Choisissez votre activité (Marche, Course, Vélo) et votre niveau (Débutant ou Intermédiares sont pour l'instant recommandés pour avoir le plus de résultats avec les moteurs d'inférence).
3.  **Conditions (faits initiaux):** Renseignez votre état de fatigue, douleurs éventuelles, la météo etc...
4.  **Recherche d'itinéraire** : Le serveur python reçoit votre localisation et obtient les itinéraires autour de vous puis une carte s'affiche avec tous les trajets trouvés.
5.  **Filtrage par système expert** :
      * Le bouton **"Lancer Chaînage Avant"** lance le Système Expert qui va déduire toutes les régles sur votre profil. Ensuite il vérifie la compatibilité de chaque trajet avec la base de faits finale et indique ceux qui sont valides pour votre profil.
      * Le bouton **"Lancer Chaînage Arrière"** lance le Système Expert qui va essayer de déduire le fait `recommandation_globale = danger`(R7, R21a, R21b) en fonction de la base de faits initiale.

      La liste d'itinéraires compatibles pour le chaînage avant et arrière s'affiche également sur le site sous forme de liste interactive qui permet de voir l'itinéraire sur la carte en cliquant dessus.

## Fichiers Supplémentaires

Si tout se déroule normalement, les fichiers suivants sont crées lors de l'utilisation de l'interface utilisateur :

  * **`itineraires.lisp`** : Base de données contenant les trajets trouvés.
  * **`faits.lisp`** : Base de faits contenant le profil utilisateur.

-----

*Projet réalisé dans le cadre de l'UV IA01 - Université de Technologie de Compiègne.*