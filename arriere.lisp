;; =============================================================================
;; CHARGEMENT DES DONNÉES
;; =============================================================================

(load "faits.lisp")       ;; Définit *faits-utilisateur* (crée par le fichier python)
(load "itineraires.lisp") ;; Définit *base-itineraires* (crée par le fichier python)
(load "baseDeRegle.lisp") ;; Définit *base-de-regles* et fonctions de service

;; =============================================================================
;; CHAÎNAGE ARRIÈRE : MOTEUR D'INFÉRENCE EN PROFONDEUR D'ABORD (DFS)
;; =============================================================================

(defun trouver-regles-concluant-sur (but bdr)
  "Trouve les règles qui concluent sur un attribut avec la bonne valeur."
  (let ((attribut-cible (car but))
        (valeur-cible (cadr but))
        (candidates nil))
    
    (dolist (regle bdr)
      (let ((conclusions (caddr regle)))
        (dolist (c conclusions)
          ;; On analyse la conclusion (ATTR VAL) ou (ACTION ATTR VAL)
          (let ((attr (if (member (car c) '(AJOUTER MULTIPLIER)) (cadr c) (car c)))
                (val (if (member (car c) '(AJOUTER MULTIPLIER)) (caddr c) (cadr c))))
            
            ;; On vérifie l'attribut et la valeur
            (when (and (equal attr attribut-cible)
                       (equal val valeur-cible))
              (push regle candidates)
              (return)))))) ;; return pour sortir de la boucle interne dès qu'on trouve une conclusion correspondante
    (reverse candidates)))

(defun verifier-et (premisses bdf bdr profondeur)
  "Vérifie si TOUTES les prémisses sont vraies."
  (dolist (condition premisses)
    (let ((op (car condition))
          (attr (cadr condition))
          (val (caddr condition)))
      
      ;; Si c'est une condition simple (equal), on lance une sous-recherche
      (if (equal op 'equal)
          (unless (verifier-ou (list attr val) bdf bdr profondeur)
            (return-from verifier-et nil))
          
          ;; Si c'est complexe (>, member...), on vérifie juste dans la BDF actuelle
          (unless (verifier-condition condition bdf)
            (return-from verifier-et nil)))))
  t)

(defun verifier-ou (but bdf bdr &optional (i 0))
  "Tente de vérifier un but (Attribut . Valeur). Renvoie T ou NIL."
  (let ((attribut (car but))
        (valeur-cible (cadr but)))
    
    ;; Affichage avec indentation dynamique (~V@t utilise i)
    (format t "~%~V@t? BUT : Vérifier ~A = ~A" i attribut valeur-cible)

    ;; Si le fait est déjà dans la base
    (let ((valeur-reelle (lire-fait attribut bdf)))
      (when valeur-reelle
        (if (equal valeur-reelle valeur-cible)
            (progn (format t " -> OUI (Dans la base : ~A)~%" valeur-reelle) (return-from verifier-ou t))
            (progn (format t " -> NON (Base contient ~A)~%" valeur-reelle) (return-from verifier-ou nil)))))

    ;; Sinon on cherche des règles qui  concluent sur ce fait
    (let ((candidats (trouver-regles-concluant-sur but bdr)))
      (if (null candidats)
          (progn (format t " -> ECHEC (Aucune règle)~%") nil)
          
          ;; On teste les règles
          (dolist (regle candidats)
            ;; On augmente l'indentation pour l'affichage de la règle
            (format t "~%~V@t> Test Règle ~A" (+ i 2) (car regle))
            
            ;; Appel récursif à verifier-et 
            (if (verifier-et (cadr regle) bdf bdr (+ i 4))
                (progn
                  (format t "~%~V@t> SUCCÈS Règle ~A : On déduit ~A = ~A" (+ i 2) (car regle) attribut valeur-cible)
                  (setq *faits-utilisateur* (ajouter-fait attribut valeur-cible *faits-utilisateur*)) 
                  (return-from verifier-ou t))
                (format t "~%~V@t> ECHEC Règle ~A" (+ i 2) (car regle))))))))

;; =============================================================================
;; LANCEMENT PRINCIPAL (sur la condition recommandation_globale = danger)
;; =============================================================================

(format t "--- DÉBUT CHAÎNAGE ARRIÈRE ---~%")

;; BUT : On veut savoir si c'est DANGEREUX
(defparameter *but-final* '(recommandation_globale danger))

(if (verifier-ou *but-final* *faits-utilisateur* *base-de-regles* 0)
    (format t "~%>>> CONCLUSION : Sortie jugée DANGEREUSE.~%")
    (format t "~%>>> CONCLUSION : Pas de danger critique détecté par le système.~%"))

;; =============================================================================
;; FILTRAGE ET RECOMMANDATION DES ITINÉRAIRES (uniquement ceux qui ne sont pas dangereux)
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

(format t "~%--- FILTRAGE ---~%")
(filtrer-itineraires *base-itineraires* *faits-utilisateur*)