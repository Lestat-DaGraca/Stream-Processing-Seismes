# StreamProcessingG2

**Description du projet :**

Le projet Real-Time Earthquake Monitoring System vise à mettre en place une architecture complète d’ingestion et d’exploitation de données en temps réel à partir de l’API sismique officielle de la USGS (United States Geological Survey).
Ce projet illustre la conception d’un pipeline de traitement en flux continu capable de recevoir, traiter et afficher des données sans stockage persistant.

L’objectif principal est d’analyser un flux infini de données pour produire des indicateurs utiles, comme la moyenne des magnitudes, la détection d’anomalies ou la génération d’alertes, tout en expérimentant des traitements plus complexes tels que le clustering.

Le système s’appuie sur un ensemble cohérent de technologies :

- Apache Kafka pour l’ingestion et la diffusion des flux,
- Faust pour le traitement en temps réel,
- Flask pour l’exposition des données via une API et une interface web,
- Scikit-learn pour l’analyse avancée des données (clustering).

Ce projet a pour vocation de démontrer la scalabilité, la fiabilité et la réactivité d’un système de traitement de données en temps réel, tout en permettant une visualisation directe des événements sismiques sur une interface web interactive.

----

## Fonctionnalités

- [X] **Ingestion des données depuis l’API USGS en continu via Kafka**
- [X] **Traitement en flux des données (calculs, moyennes, anomalies) avec Faust**
- [X] **Détection d’événements majeurs et génération d’alertes automatiques**
- [X] **Analyse avancée avec algorithmes de clustering (scikit-learn)**
- [X] **Exposition des résultats via une API REST et WebSocket Flask**
- [X] **Visualisation web dynamique avec HTML, CSS et JavaScript**

----

| Composant                   | Technologie                  | Rôle                                           |
| --------------------------- | ---------------------------- | ---------------------------------------------- |
| **Langage principal**       | Python 3.11                  | Développement du pipeline et de l’API          |
| **Middleware de messages**  | Apache Kafka                 | Transmission et diffusion des flux de données  |
| **Traitement en flux**      | Faust (faust-streaming)      | Calculs temps réel et agrégation               |
| **Producteur de données**   | Kafka-Python                 | Récupération des données de l’API USGS         |
| **API & Interface web**     | Flask, HTML, CSS, JavaScript | Exposition et affichage en temps réel          |
| **Analyse avancée**         | scikit-learn, NumPy          | Clustering et traitements statistiques         |
| **Visualisation graphique** | Chart.js, Leaflet.js         | Affichage des indicateurs et cartes dynamiques |

----

## Guide d'installation

### Prérequis

1. **Python 3.11**
2. **Java 21 (pour Kafka)**
3. **Apache Kafka installé localement**
4. **Connexion Internet (pour l’API USGS)**

### Étapes d’installation

1. Cloner le projet :
```bash
git clone https://gitlabvigan.iem/m2projettutore2025-2026-groupe2/streamprocessingg2.git
cd streamprocessingg2
```

2. Créer et activer un environnement virtuel :
```bash
python -m venv venv
venv\Scripts\activate   # sous Windows
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

4. Démarrer les services Kafka :
```bash
.\bin\windows\zookeeper-server-start.bat .\config\zookeeper.properties
.\bin\windows\kafka-server-start.bat .\config\server.properties
```

5. Créer les topic Kafka :
exemple :
```bash
.\bin\windows\kafka-topics.bat --create --topic earthquakes --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
CMD = .\bin\windows\kafka-topics.bat --create --topic earthquakes \ --bootstrap-server localhost:9092 \ --partitions 1 --replication-factor 1
CMD = .\bin\windows\kafka-topics.bat --create --topic usgs_last_day \ --bootstrap-server localhost:9092 \ --partitions 1 --replication-factor 1
CMD = .\bin\windows\kafka-topics.bat --create --topic usgs_significant_week \ --bootstrap-server localhost:9092 \ --partitions 1 --replication-factor 1
CMD = .\bin\windows\kafka-topics.bat --create --topic usgs_by_region \ --bootstrap-server localhost:9092 \ --partitions 8 --replication-factor 1
```
6. Lancer le producteur Kafka (récupération API USGS) :
```bash
python -m producers.usgs_producer
```

7. Lancer le consommateur Faust :
```bash
cd faust_app
faust -A main worker -l info
```

8. Lancer l’application Flask :
```bash
cd flask_app
flask run
```

L’application est accessible sur : http://localhost:5000

---

## Commandes utiles

| Action                          | Commande                                                                                        |
| ------------------------------- | ----------------------------------------------------------------------------------------------- |
| Activer l’environnement virtuel | `venv\Scripts\activate`                                                                         |
| Lancer l’API Flask              | `flask run`                                                                                 |
| Démarrer le worker Faust        | `faust -A main worker -l info`                                                          |
| Lancer Zookeeper                | `.\bin\windows\zookeeper-server-start.bat .\config\zookeeper.properties`                        |
| Lancer Kafka                    | `.\bin\windows\kafka-server-start.bat .\config\server.properties`                               |
| Créer le topic Kafka            | `.\bin\windows\kafka-topics.bat --create --topic earthquakes --bootstrap-server localhost:9092` |
| Vérifier la version de Java     | `java --version`                                                                                |


---

## Communication & Gestion de projet

- **Discord**
- **OpenProject** : [https://op.iem/projects/m2projettutore2025-2026-groupe2/](#)

---

## Équipe

Ce projet est réalisé par une équipe de 6 membres :

- **Chef d’équipe / Responsable d’équipe** : Anthony MICHAUD, responsable de la coordination, de la répartition des tâches, et de la communication.
- **Développeurs** : Kévin PRADIER, Sebastien MOREL, Aichetou N-DIAYE, Lestat ROBERTO-DA-GRACA, Matthieu DETAIL

