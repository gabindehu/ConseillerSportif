;; =============================================================================
;; CHARGEMENT DES DONNÉES
;; =============================================================================

(load "faits.lisp")       ;; Définit *faits-utilisateur* (crée par le fichier python)
(load "itineraires.lisp") ;; Définit *base-itineraires* (crée par le fichier python)
(load "baseDeRegle.lisp") ;; Définit *base-de-regles* et fonctions de service

;; =============================================================================
;; MOTEUR D'INFÉRENCE : CHAÎNAGE AVANT EN LARGEUR D'ABORD (BFS)
;; =============================================================================

;; Logique de vérification sur une condition (une règle peut avoir plusieurs conditions)
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

;; Vérification d'une règle complète (toutes les conditions)
(defun verifier-regle (premisses bdf)
  (let ((resultat t))
    
    (dolist (p premisses)
      (if (not (verifier-condition p bdf))
          (progn
            ;; Si une condition est fausse, on note l'échec et on sort
            (setq resultat nil)
            (return)))) 
            
    resultat)) 

(defun appliquer-conclusions (conclusions bdf)
  "Applique les conclusions des règles."
  (dolist (c conclusions)
    (let ((action-ou-attr (car c)))
      
      (cond
        ;; Cas AJOUTER
        ((equal action-ou-attr 'AJOUTER)
         (let ((attr (cadr c))
               (val (caddr c)))
           (let ((existant (assoc attr bdf)))
             (if existant
                 (pushnew val (cadr existant)) 
                 (push (list attr (list val)) bdf)))
           (format t "   -> Ajout : ~A dans ~A~%" val attr)))
        
        ;; Cas MULTIPLIER
        ((equal action-ou-attr 'MULTIPLIER)
         (let ((attr (cadr c))
               (facteur (caddr c)))
           (let ((ancienne-val (lire-fait attr bdf)))
             (when (numberp ancienne-val)
               (let ((nouvelle-val (* ancienne-val facteur)))
                 (setq bdf (ajouter-fait attr nouvelle-val bdf))
                 (format t "   -> Modif : ~A (~A -> ~A)~%" attr ancienne-val nouvelle-val))))))
        
        ;; Cas (ATTR VAL)
        (t
         (let ((attr action-ou-attr)
               (valeur (cadr c)))
           
           (setq bdf (ajouter-fait attr valeur bdf))
           (format t "   -> Déduction : ~A = ~A~%" attr valeur))))))
  bdf)

(defun chainage-avant (bdf bdr)
  (format t "~%--- DÉMARRAGE DU CHAINAGE AVANT ---~%")
  (let ((nouveaux-faits t)
        (regles-actives bdr))
    
    (loop while (and nouveaux-faits (not (equal (lire-fait 'stop_evaluation bdf) 'vrai))) do
      (setq nouveaux-faits nil)
      (let ((regles-restantes nil))
        (dolist (regle regles-actives)
          (let ((id (car regle)) (premisses (cadr regle)) (conclusions (caddr regle)))
            
            (if (verifier-regle premisses bdf)
                (progn
                  (format t ">> Règle ~A déclenchée.~%" id)
                  (setq bdf (appliquer-conclusions conclusions bdf))
                  (setq nouveaux-faits t))
                ;; Sinon on garde la règle
                (push regle regles-restantes))))
        (setq regles-actives (reverse regles-restantes))))
    
    (format t "--- FIN INFÉRENCE ---~%")
    bdf))

;; =============================================================================
;; FILTRAGE ET RECOMMANDATION DES ITINÉRAIRES
;; =============================================================================

(defun filtrer-itineraires (liste-itineraires bdf)
  (format t "~%--- ANALYSE DES ITINÉRAIRES ---~%")
  
  ;; Récupération du profil déduit
  (let ((act-user (lire-fait 'activite bdf))
        (dist-max (lire-fait 'distance_max_recommande bdf))
        (deniv-max (lire-fait 'denivele_max_recommande bdf))
        (risque-terrain (lire-fait 'risque_terrain bdf))
        (reco-globale (lire-fait 'recommandation_globale bdf)))

    ;; Si danger_global (R21) on ne vérifie aucun itinéraire
    (if (equal reco-globale 'danger)
        (format t "ALERTE : Sortie déconseillée (Danger détecté). Aucun itinéraire proposé.~%")
        
        ;; Sinon on teste les itinéraires
        (progn
          (unless dist-max (setq dist-max 9999)) ;; Sécurité
          (unless deniv-max (setq deniv-max 9999))
          
          (dolist (it liste-itineraires)
            (let ((id (nth 0 it)) (nom (nth 1 it)) (act (nth 2 it)) 
                  (diff (nth 3 it)) (terrain (nth 4 it)) (dist (nth 5 it)) (deniv (nth 6 it)))
              
              ;; On n'affiche que ceux de la bonne activité
              (when (or (equal act act-user)
                        (and (equal act-user 'course) (equal act 'marche)))
                (format t "Evaluation Itinéraire ~A (~Akm, ~Am)... " id dist deniv)
                
                ;; Implémentation R19 : Vérification des seuils
                (let ((adéquation-difficile (or (> dist dist-max) (> deniv deniv-max)))
                      (difficulte-ajustee nil))
                  
                  ;; Implémentation R20 : Si adéquation difficile OU risque terrain élevé -> Très difficile
                  (if (or adéquation-difficile (equal risque-terrain 'eleve))
                      (setq difficulte-ajustee 'tres_difficile)
                      (setq difficulte-ajustee diff))
                  
                  (if (equal difficulte-ajustee 'tres_difficile)
                      (format t "REJETÉ (Trop difficile/Risqué)~%")
                      (format t "VALIDÉ (Difficulté : ~A)~%" difficulte-ajustee))))))))))

;; =============================================================================
;; LANCEMENT PRINCIPAL
;; =============================================================================

;; 1. Afficher l'état initial
(format t "Etat initial : ~A~%" *faits-utilisateur*)

;; 2. Lancer le moteur
(let ((bdf-finale (chainage-avant *faits-utilisateur* *base-de-regles*)))
  
  ;; 3. Afficher les conclusions clés
  (format t "~%RÉSULTATS DU CHAÎNAGE AVANT :~%")
  (format t "- Distance Max : ~A km~%" (lire-fait 'distance_max_recommande bdf-finale))
  (format t "- Dénivelé Max : ~A m~%" (lire-fait 'denivele_max_recommande bdf-finale))
  (format t "- Risque Météo : ~A~%" (lire-fait 'risque_meteo bdf-finale))
  (format t "- Equipement   : ~A~%" (lire-fait 'equipement_conseille bdf-finale))
  
  ;; 4. Filtrer les trajets
  (filtrer-itineraires *base-itineraires* bdf-finale))