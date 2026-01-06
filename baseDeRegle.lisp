;; =============================================================================
;; FONCTIONS DE SERVICE
;; =============================================================================

;; --- Fonctions de service pour la Base de Faits ---

(defun lire-fait (attribut bdf)
  "Lit une valeur dans la BDF au format liste (KEY VAL)."
  (let ((fait (assoc attribut bdf)))
    (if fait
        (cadr fait)
        nil)))

(defun ajouter-fait (attribut valeur bdf)
  "Ajoute ou met à jour un fait sous forme de liste (ATTRIBUT VALEUR)."
  (let ((existant (assoc attribut bdf)))
    (if existant
        (setf (cadr existant) valeur)  
        (push (list attribut valeur) bdf))) 
  bdf)

(defun ajouter-a-la-liste (attribut valeur bdf)
  "Ajoute une valeur à une liste (pour l'équipement conseillé)."
  (let ((existant (assoc attribut bdf)))
    (if existant
        (pushnew valeur (cdr existant)) 
        (push (cons attribut (list valeur)) bdf)))
  bdf)

(defun fait-contient (attribut valeur bdf)
  "Vérifie si une liste dans la BDF contient une valeur donnée."
  (let ((liste (lire-fait attribut bdf)))
    (if (listp liste)
        (member valeur liste)
        (equal liste valeur))))

(defun verifier-condition (condition bdf)
  "Vérifie une prémisse."
  (let* ((op (car condition))
         (attribut (cadr condition))
         (valeur-cible (caddr condition))
         (valeur-reelle (lire-fait attribut bdf)))
    
    (cond
      ((equal op 'CONTIENT) (fait-contient attribut valeur-cible bdf))
      ((null valeur-reelle) nil) ;; Si le fait n'existe pas, c'est faux
      (t (funcall op valeur-reelle valeur-cible)))))

;; =============================================================================
;; BASE DE RÈGLES
;; =============================================================================
;; Forme : (ID (PREMISSES) (CONCLUSIONS))
;; Les conclusions peuvent être de type : (AJOUTER attr val) ou (MULTIPLIER attr val)

(defparameter *base-de-regles*
  '(
    ;; --- R1 à R4 : Seuils Physiques (Calculs pour le Chaînage Avant) ---
    (R1 ((equal niveau_utilisateur debutant) (equal activite course))
        ((distance_max_recommande 8) (denivele_max_recommande 150)))
    (R2 ((equal niveau_utilisateur intermediaire) (equal activite course))
        ((distance_max_recommande 15) (denivele_max_recommande 400)))
    (R2bis ((equal niveau_utilisateur intermediaire) (equal activite velo))
        ((distance_max_recommande 50) (denivele_max_recommande 600)))
    (R3 ((equal niveau_utilisateur debutant) (equal activite marche))
        ((distance_max_recommande 12) (denivele_max_recommande 300)))
    (R3bis ((equal niveau_utilisateur intermediaire) (equal activite marche))
           ((distance_max_recommande 20) (denivele_max_recommande 600)))
    (R4 ((equal niveau_utilisateur debutant) (equal activite velo))
        ((distance_max_recommande 25) (denivele_max_recommande 200)))

    ;; --- R5 & R6 : Modificateurs (Fatigue/Douleur) ---
    (R5 ((equal etat_fatigue vrai))
        ((MULTIPLIER distance_max_recommande 0.6) 
         (MULTIPLIER denivele_max_recommande 0.6)))
    (R6 ((equal douleur legere))
        ((MULTIPLIER distance_max_recommande 0.7) 
         (MULTIPLIER denivele_max_recommande 0.7)))

    ;; =========================================================================
    ;; RÈGLES DE DANGER (Cibles du Chaînage Arrière)
    ;; =========================================================================

    ;; --- R7 : Douleur Forte = STOP IMMÉDIAT ---
    (R7 ((equal douleur forte))
        ((recommandation_globale danger)))

    ;; --- R8 : Météo Extrême (Orage) ---
    (R8a ((equal meteo orage))
         ((risque_meteo eleve)))
    
    (R8b ((equal meteo vent_fort))
         ((risque_meteo eleve)))

    ;; --- R13 : Vent Fort ---
    ;; Cas A : Vent fort est dangereux pour tout le monde
    (R13a ((equal vent fort)) 
          ((risque_meteo eleve)))
    
    ;; Cas B : Vent MOYEN est dangereux spécifiquement en vélo
    (R13b ((equal vent moyen) (equal activite velo))
          ((risque_meteo eleve)))

    ;; --- R15 : Danger Déshydratation (Longue distance sans eau) ---
    (R15 ((equal objectif_distance longue) (equal eau faux))
         ((risque_securite_perso eleve)))

    ;; --- R18 : Danger Technique (VTT sur technique sans équipement) ---
    (R18 ((equal activite velo) (equal niveau_utilisateur debutant) (equal equipement_adapte faux))
         ((risque_securite_perso eleve)))

    ;; =========================================================================
    ;; RÈGLES INTERMÉDIAIRES (Lien vers Danger)
    ;; =========================================================================

    ;; Si Risque Météo Élevé -> DANGER
    (R21a ((equal risque_meteo eleve)) 
          ((recommandation_globale  danger)))
    
    ;; Si Risque Sécurité Perso Élevé -> DANGER
    (R21b ((equal risque_securite_perso eleve)) 
          ((recommandation_globale  danger)))


    ;; --- Autres règles d'équipement (Chaînage Avant surtout) ---
    (R9 ((equal meteo pluie_forte))
        ((risque_meteo modere) (AJOUTER equipement_conseille veste_pluie)))
    (R10 ((> temperature 30))
        ((risque_meteo  modere) (AJOUTER equipement_conseille eau+)))
    (R11a ((equal meteo pluie_faible)) ((etat_sol_probable mouille)))
    (R11b ((equal meteo pluie_forte))  ((etat_sol_probable mouille)))
))