# T2A Assistant — Project Notes

## Project Idea
App mobile (payante, ~60€/an ou 8€/mois) pour médecins. Interface vocale par défaut.
Le médecin décrit son opération/activité → l'app trouve le meilleur codage CCAM/CIM-10 compatible, sans erreurs de rejet.
Export Excel par période pour la redevance administrative.

## Origin
- Ami neurochir **Rodrigue (Angers)** signale que aideaucodage.fr conseille parfois des codes qui se font rejeter
- Problème : les rejets ne viennent pas de règles régionales mais de l'interprétation locale (DIM, logiciel SIH, historique de contrôles)
- Les règles T2A sont **100% nationales** (ATIH), mais l'application varie par établissement

---

## Domain Knowledge (2026-02-19)

### Architecture du codage T2A
- **ATIH** = source de vérité (CIM-10 FR, CCAM descriptive, Guides méthodologiques, Fonction Groupage)
- **UNCAM/Assurance Maladie** = CCAM tarifante + règles de facturation
- **Rejets locaux** causés par : DIM local (interprétation), logiciel SIH (contrôles bloquants), UCR régionale (ciblage contrôles), historique sanctions
- Détail complet dans `TECHNICAL_FEASIBILITY.md`

### Layers de contrôle
1. Logiciel SIH (temps réel, bloquants locaux)
2. DIM interne (qualité, interprétation)
3. UCR régionale + ARS (programme de contrôle)
4. National : DGOS/DSS/ATIH/CNAM (priorités, outils DATIM/OVALIDE)

---

## Technical Feasibility (2026-02-19)

### Data Sources — Résumé

| Donnée | Dispo? | Machine-readable? | Gratuit? | Usage commercial? |
|--------|--------|-------------------|----------|-------------------|
| CCAM codes + descriptions | OUI | OUI (Excel, CSV, FHIR, OWL) | OUI | OUI (Licence Ouverte v2.0) |
| CCAM tarifs | OUI | OUI (Excel, NX) | OUI | OUI |
| CIM-10 FR | OUI | OUI (ClaML XML, FHIR, OWL) | OUI | **PROBLÈME** (CC BY-NC-ND 3.0 = pas commercial) |
| Incompatibilités CCAM (~15K) | PARTIEL | PARTIEL (Excel complément + PDF) | OUI | OUI (extraction manuelle nécessaire) |
| Fonction Groupage | OUI | OUI (code source C) | **NON** | OUI (licence payante ATIH/DeCLic) |
| Tarifs GHS | OUI | OUI (CSV, Excel) | OUI | OUI |
| Guides méthodologiques | OUI | NON (PDF seulement) | OUI | OUI |

### APIs disponibles
- **SMT FHIR** : `https://smt.esante.gouv.fr/fhir/` — CCAM + CIM-10 (gratuit, inscription)
- **SMT SPARQL** : `https://smt.esante.gouv.fr/sparql/`
- **MedShake API** : `https://api-ccam-ngap.medshake.net/` — CCAM + NGAP (open source AGPL)
- **ScanSante Open Data** : `https://www.scansante.fr/opendata` (fichiers, pas d'API)

### Fréquence de mise à jour
- **CCAM** : 4-6 fois/an (irrégulier)
- **CIM-10 FR** : annuel (décembre pour application janvier)
- **Fonction Groupage** : annuel (Q4 pour application janvier)
- **Tarifs GHS** : annuel (parfois corrections mi-année)
- **Guides méthodologiques** : annuel
- Cycle clé : **novembre-mars** (Notice Technique ATIH en novembre)

### 3 Risques critiques (UPDATED 2026-02-19)
1. **Licence CIM-10** : CC BY-NC-ND 3.0 IGO (version SMT) = usage commercial interdit. MAIS la version ATIH ClaML peut avoir des termes différents → contacter ATIH pour clarifier
2. **Fonction Groupage** : Pas de version gratuite. Code source C + tables binaires .TAB = licence payante (DeCLic, prix non public). MAIS le Manuel des GHM (3 volumes PDF + CSV) est PUBLIC et décrit l'algorithme complet. Réimplémenter en clean-room est **légalement défendable** (jurisprudence EU SAS v. WPL, C-406/10, 2012). C'est un gros effort (1000+ pages) mais faisable.
3. **Incompatibilités CCAM** : pas de fichier propre — extraction manuelle depuis PDF Annexe 6 (~15K paires) + fichier complémentaire Excel CCAM

### Décision Fonction Groupage : Build Our Own
- Le Manuel des GHM est un **document réglementaire public** (Bulletin Officiel)
- Il contient TOUT : 28 CMD, racines GHM, arbres de décision, listes CMA, exclusions
- CSV extraits disponibles gratuitement (Manuel_GHM_fichiercsv)
- Outil scrapatih (open source) extrait les données des PDFs ATIH
- Jurisprudence EU (SAS v. WPL) : les fonctionnalités/algorithmes ne sont PAS protégés par le copyright, seul le code source spécifique l'est
- **On ne peut PAS** : copier le code C de l'ATIH ni redistribuer les .TAB
- **On PEUT** : réimplémenter depuis la doc publique (Manuel des GHM)
- Validation : comparer nos résultats avec des cas connus
- Effort estimé : significatif (mois, pas jours) mais c'est un MOAT compétitif

### Réglementaire
- **Pas un dispositif médical** si positionné comme "aide au codage" (pas diagnostic)
- **HDS** : nécessaire si hébergement cloud de données patient. Utiliser un hébergeur certifié (OVH, Scaleway, Azure)
- **RGPD santé** : données de santé = catégorie spéciale. Si données patient → DPIA obligatoire
- **CIM-11** : transition prévue ~2031 en France (expérimentation 2025-2027)

---

## Competition (2026-02-19)

### Tier 1 — Enterprise AI (nos vrais concurrents)
| Acteur | Produit | Cible | Prix |
|--------|---------|-------|------|
| **Sancare** | Sancare AI | Hôpitaux (via DPI) | Enterprise (levée 2M€) |
| **Collective Thinking** | Intelligence for Health | Hôpitaux | Enterprise |
| **Ospi (ex-Alicante)** | DIMbox | Groupes hospitaliers | Enterprise |

- **UniHA** a structuré le marché via appel d'offres M_2054 (2020-2024), 3 fournisseurs retenus
- Tous nécessitent intégration DPI = pas pour le médecin individuel

### Tier 2 — Suites PMSI intégrées
- **Maincare** (CORA PMSI) — leader marché
- **Dedalus** (WebPIMs) — leader solutions PMSI France
- **Berger-Levrault** (BL.PMSI)
- Tous ciblent la direction hospitalière, pas le praticien

### Tier 3 — Outils gratuits/légers
- **aideaucodage.fr** — gratuit, recherche CCAM/CIM-10, pas de simulation groupage
- **PMSIM.fr** — gratuit, recherche CIM-10
- **PMSISoft** — analyse PMSI (lespmsi.com)

### Open Source
- **pypmsi** (Python, GPL-3) — lecture fichiers PMSI, très rapide
- **refpmsi** (R) — 82 datasets de référence PMSI
- **MedShake API-CCAM-NGAP** (PHP, AGPL) — API REST CCAM

### Gap identifié
**PERSONNE ne cible le médecin individuel avec une interface simple (vocale).** Tout le marché vise les DIM/hôpitaux avec des solutions enterprise lourdes. Le praticien est laissé avec aideaucodage.fr (gratuit mais incomplet/parfois faux).

---

## Architecture technique recommandée
1. **Terminologie** : SMT FHIR API (CCAM) + base CIM-10 auto-hébergée (ClaML XML, licence à clarifier)
2. **Tarification** : CSV/Excel ATIH, mise à jour annuelle automatisée
3. **Groupage** : Fonction Groupage ATIH licensée (C compilé) ou implémentation custom depuis tables de décision
4. **Incompatibilités** : moteur custom depuis Annexe 6 digitalisée + fichier complémentaire Excel CCAM
5. **Format données** : pypmsi (Python) ou parseur custom pour RSS/RUM
6. **Hébergement** : HDS-certifié (OVH, Scaleway, Azure)
7. **Interface vocale** : Whisper/ElevenLabs ou autre STT

---

## Contact Info
- **Sammy GAD** — sammy.gad28@gmail.com — 06 51 18 14 43
- **Rodrigue** — ami neurochir à Angers (source du pain point)

## Actions Log
- **2026-02-19** : Email envoyé à support@atih.sante.fr pour demander tarifs FG-MCO, éligibilité éditeur, modalités techniques, procédure DéCLic → EN ATTENTE DE RÉPONSE

## Docs & Code
- `PRODUCT_BRIEF.md` — Product brief complet (2026-02-19)
- `build_ccam_db.py` — Script de construction de la base SQLite CCAM
- `ccam_search.py` — Moteur de recherche CCAM + CLI interactive
- `data/ccam.db` — Base SQLite (8 271 codes, 15 060 associations, FTS5)
- `data/ccam/` — Fichiers source (CSV data.gouv + 2 Excel ATIH)

## Prototype Status (2026-02-19)
- **Base CCAM** : 8 168 codes actifs, 15 060 associations officielles ATIH + **129 643 associations fréquentes PMSI**
- **Associations PMSI** : Scrapées depuis aideaucodage.fr (8 168 codes), validées contre ATIH
  - 4 472 "verified" (présentes dans ATIH officiel)
  - 63 034 "same_chapter" (même région anatomique)
  - 62 137 "cross_chapter" (autre région, mais fréquentes en pratique)
  - 10 783 supprimées (codes invalides/expirés)
- **Recherche** : FTS5 full-text, accent-insensitive, multi-stratégie (AND -> OR -> LIKE)
- **Billing plan** : acte principal + gestes officiels ATIH + associations fréquentes PMSI, tri par ICR, badges confiance
- **Web UI** : FastAPI + HTML/CSS/JS dark theme, recherche temps réel, plan de facturation avec checkboxes, total ICR dynamique
- **DEPLOYE** : https://t2a-assistant.onrender.com (Render free tier, Docker, 2026-02-19)
  - GitHub repo : https://github.com/Yunaae/t2a-assistant (public)
  - Note : free tier = sleep après 15 min inactivité, ~30-50s de cold start
  - **IMPORTANT** : Auto-deploy PAS activé. Utiliser "Manual Deploy" dans le dashboard Render.

## Feedback Rodrigue (2026-02-19)
- **Pas besoin de CIM-10/diagnostics** pour l'instant — les actes (CCAM) sont le nerf de la guerre
- **Core need** : quand il cherche une opération, voir la meilleure combinaison d'actes pour facturer le maximum, dans le bon ordre
- **Problème aideaucodage.fr** : propose parfois des associations erronées → notre plus-value = associations validées

## Pipeline de données
- `scrape_associations.py` — Scraper aideaucodage.fr (8 168 codes, ~2.5h à 1 req/s)
- `validate_associations.py` — Validation contre ATIH (codes existants, actifs, confiance)
- `integrate_associations.py` — Intégration dans SQLite (table `frequent_associations`)
- `data/frequent_associations.json` — Données brutes scrapées (140 426 paires)
- `data/validated_associations.json` — Données validées (129 643 paires)

## Next Steps
- [ ] **EN ATTENTE** : Réponse ATIH sur licence FG-MCO (tarif + éligibilité)
- [ ] Clarifier licence CIM-10 (2e email ATIH ou dans la réponse)
- [ ] **Feedback Rodrigue** sur le prototype avec associations fréquentes
- [ ] Choisir stack mobile (React Native vs Flutter)
- [ ] Ajouter CIM-10 (dépend licence)
- [ ] Simulateur groupage GHM/GHS (dépend FG)
- [x] Product brief (2026-02-19)
- [x] Valider le concept avec Rodrigue — prêt à payer 60€/an
- [x] Prototyper recherche CCAM + vérification incompatibilités (2026-02-19)
- [x] Web UI + déploiement Render (2026-02-19)
- [x] Scraper + valider + intégrer associations fréquentes PMSI (2026-02-19)

---

## Key URLs
- ATIH CCAM : https://www.atih.sante.fr/ccam-descriptive-usage-pmsi-2025
- ATIH CIM-10 ClaML : https://www.atih.sante.fr/cim-10-fr-usage-pmsi-au-format-claml
- ATIH Fonction Groupage : https://www.atih.sante.fr/fonction-groupage-mco-2026
- ATIH Tarifs : https://www.atih.sante.fr/tarifs-mco-et-had
- SMT FHIR : https://smt.esante.gouv.fr/fhir/
- DeCLic : https://declic.atih.sante.fr/
- data.gouv.fr CCAM : https://www.data.gouv.fr/datasets/ccam-ameli
- pypmsi : https://github.com/GuillaumePressiat/pypmsi
- MedShake API : https://github.com/MedShake/API-CCAM-NGAP
