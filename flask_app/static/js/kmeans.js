document.addEventListener('DOMContentLoaded', function() {
    console.log("🗺️ Initialisation K-Means incrémental...");
  
    // Carte
    const map = L.map('map').setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap'
    }).addTo(map);
    
    setTimeout(() => map.invalidateSize(), 100);

    // Couleurs clusters
    const colors = [
        '#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6',
        '#ec4899', '#14b8a6', '#f97316', '#06b6d4', '#84cc16'
    ];

    // Layers séparées et persistantes
    let markersLayer = L.featureGroup().addTo(map);
    let centroidsLayer = L.featureGroup().addTo(map);
    
    // État local
    let earthquakesData = [];
    let currentClusteringActive = false;
    let incrementalMode = false;  // Mode incrémental activé/désactivé
    let lastEarthquakeCount = 0;
    let currentK = 3;  // K actuel du clustering
    let longPollingActive = false;  // Long polling en cours
    let abortController = null;  // Pour annuler les requêtes

    // DOM
    const kSlider = document.getElementById('k-slider');
    const kValue = document.getElementById('k-value');
    const applyBtn = document.getElementById('apply-clustering');
    const resetBtn = document.getElementById('reset-btn');
    const incrementalToggle = document.getElementById('incremental-toggle');
    const totalCount = document.getElementById('total-count');
    const clusterCount = document.getElementById('cluster-count');
    const clustersContainer = document.getElementById('clusters-container');

    // Sync slider
    kSlider.addEventListener('input', (e) => {
        const newK = parseInt(e.target.value);
        kValue.textContent = newK;
        
        // Si K change et que le mode incrémental est actif, le désactiver
        if (incrementalMode && newK !== currentK) {
            console.log(` K modifié (${currentK} → ${newK}), désactivation du mode incrémental`);
            incrementalMode = false;
            incrementalToggle.checked = false;
            updateToggleStatus();
        }
    });

    // Gestion du toggle incrémental
    incrementalToggle.addEventListener('change', async (e) => {
        incrementalMode = e.target.checked;
        
        if (incrementalMode) {
            // Activation du mode incrémental
            const k = parseInt(kSlider.value);
            
            if (!currentClusteringActive) {
                // Si pas de clustering actif, en démarrer un
                console.log(' Activation du mode incrémental : démarrage d\'un clustering...');
                await applyClustering();
            } else if (k !== currentK) {
                // Si K a changé, refaire un clustering complet
                console.log(` K modifié (${currentK} → ${k}), reclustering complet...`);
                currentK = k;
                await applyClustering();
            } else {
                console.log(' Mode incrémental activé');
            }
            
            // DÉMARRER LE LONG POLLING
            startLongPolling();
            
        } else {
            console.log(' Mode incrémental désactivé');
            
            // ARRÊTER LE LONG POLLING
            stopLongPolling();
        }
        
        updateToggleStatus();
    });

    // Mettre à jour le statut visuel du toggle
    function updateToggleStatus() {
        const toggleContainer = incrementalToggle.parentElement;
        if (incrementalMode) {
            toggleContainer.classList.add('toggle-active');
        } else {
            toggleContainer.classList.remove('toggle-active');
        }
    }

    // Fonction pour afficher séismes
    function displayEarthquakes(earthquakes, withClusters = false) {
        markersLayer.clearLayers();

        if (earthquakes.length === 0) return;

        earthquakes.forEach(eq => {
            const color = withClusters && eq.cluster !== undefined 
                ? colors[eq.cluster % colors.length] 
                : '#3b82f6';
            
            const marker = L.circleMarker([eq.latitude, eq.longitude], {
                radius: Math.max(5, eq.magnitude * 1.5),
                fillColor: color,
                color: 'white',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.7
            });

            marker.bindPopup(`
                <strong>${eq.place}</strong><br>
                Magnitude: <span style="color: #ef4444;">${eq.magnitude}</span><br>
                Région: ${eq.region}<br>
                Date: ${new Date(eq.time).toLocaleString('fr-FR')}
                ${withClusters && eq.cluster !== undefined ? `<br>Cluster: ${eq.cluster + 1}` : ''}
            `);
            
            markersLayer.addLayer(marker);
        });

        if (markersLayer.getLayers().length > 0) {
            const bounds = markersLayer.getBounds();
            map.fitBounds(bounds.pad(0.1));
        }
    }

    // Fonction pour afficher centroïdes
    function displayCentroids(centers) {
        centroidsLayer.clearLayers();

        centers.forEach(c => {
            const color = colors[c.id % colors.length];
            
            const marker = L.marker([c.latitude, c.longitude], {
                icon: L.divIcon({
                    className: 'centroid-marker',
                    html: `<div style="
                        background: ${color};
                        width: 35px; 
                        height: 35px;
                        border-radius: 50%;
                        border: 3px solid white;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-weight: bold;
                        font-size: 16px;
                    ">★</div>`,
                    iconSize: [35, 35],
                    iconAnchor: [17.5, 17.5]
                }),
                zIndexOffset: 1000
            });

            marker.bindPopup(`
                <strong>Centre Cluster ${c.id + 1}</strong><br>
                Coordonnées: ${c.latitude.toFixed(2)}°, ${c.longitude.toFixed(2)}°
            `);
            
            centroidsLayer.addLayer(marker);
        });

        console.log(`✅ ${centers.length} centroïdes affichés`);
    }

    // Afficher les clusters dans la liste
    function displayClusters(clustersData) {
        let html = '';

        clustersData.forEach(cluster => {
            const color = colors[cluster.id % colors.length];
            
            html += `
                <div class="cluster-card" style="border-left-color: ${color};">
                    <div class="cluster-header">
                        <div class="cluster-title">
                            <div class="cluster-badge" style="background: ${color};"></div>
                            <span>Cluster ${cluster.id + 1}</span>
                        </div>
                        <div class="cluster-count">${cluster.count} séisme${cluster.count > 1 ? 's' : ''}</div>
                    </div>
                    <div class="cluster-stats">
                        📍 Centre: ${cluster.center.latitude.toFixed(2)}°, ${cluster.center.longitude.toFixed(2)}°<br>
                        📊 Magnitude moyenne: ${cluster.avg_magnitude}
                    </div>
                    <div class="eq-list">
                        ${cluster.earthquakes.map(eq => `
                            <div class="eq-item-small">
                                <div>
                                    <strong>${eq.place}</strong><br>
                                    <small>${new Date(eq.time).toLocaleString('fr-FR')}</small>
                                </div>
                                <div class="eq-magnitude-small">M${eq.magnitude}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });

        clustersContainer.innerHTML = html;
    }

    // Charger les données initiales
    async function loadData() {
        try {
            const res = await fetch('/kmeans/earthquakes');
            const data = await res.json();

            earthquakesData = data;
            
            // Si pas de clustering actif, afficher en bleu
            if (!currentClusteringActive) {
                displayEarthquakes(earthquakesData);
            }
            
            totalCount.textContent = earthquakesData.length;
            
            if (earthquakesData.length > 0) {
                kSlider.max = Math.min(10, earthquakesData.length);
            }

            console.log(` ${earthquakesData.length} séismes chargés`);

        } catch (err) {
            console.error(" Erreur:", err);
        }
    }

    // Long Polling 
    async function startLongPolling() {
        longPollingActive = true;
        console.log(' Long polling démarré');
        
        while (longPollingActive && incrementalMode) {
            try {
                // Créer un AbortController pour pouvoir annuler
                abortController = new AbortController();
                
                console.log(' En attente de nouveaux séismes...');
                
                // Appel long polling (attend max 120s)
                const res = await fetch('/kmeans/wait-for-update', {
                    signal: abortController.signal
                });
                
                const data = await res.json();
                
                if (data.has_update) {
                    console.log(' Nouveau séisme détecté !');
                    
                    // Récupérer la mise à jour incrémentale
                    await performIncrementalUpdate();
                } else {
                    console.log(' Timeout (120s) - aucun nouveau séisme');
                }
                
            } catch (err) {
                if (err.name === 'AbortError') {
                    console.log(' Long polling annulé');
                    break;
                } else {
                    console.error(' Erreur long polling:', err);
                    // Attendre 5s avant de réessayer en cas d'erreur
                    await new Promise(resolve => setTimeout(resolve, 5000));
                }
            }
        }
        
        console.log(' Long polling arrêté');
    }
    
    function stopLongPolling() {
        longPollingActive = false;
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
    }
    
    async function performIncrementalUpdate() {
        try {
            const res = await fetch('/kmeans/update');
            const data = await res.json();

            if (data.update_type === 'no_change') {
                console.log(' Pas de nouveaux séismes');
                return;
            }

            if (data.update_type === 'full_reclustering') {
                console.log(' Reclustering complet (20 minutes écoulées)');
            } else if (data.update_type === 'incremental') {
                console.log(` Mise à jour incrémentale : ${data.updates.length} nouveaux séismes`);
                
                // Logger les détails de propagation
                data.updates.forEach(update => {
                    console.log(
                        `  - ${update.earthquake} → Cluster ${update.cluster_assigned + 1} ` +
                        `(déplacement: ${(update.centroid_shift * 100).toFixed(2)}%, ` +
                        `propagation: ${update.propagation_type}, ` +
                        `réassignations: ${update.points_reassigned})`
                    );
                });
            }

            // Mettre à jour l'affichage
            displayEarthquakes(data.earthquakes, true);
            displayCentroids(data.centers);
            displayClusters(data.clusters);
            totalCount.textContent = data.total_earthquakes;
            clusterCount.textContent = data.n_clusters;

        } catch (err) {
            console.error(" Erreur mise à jour:", err);
        }
    }

    // Appliquer le clustering (complet)
    async function applyClustering() {
        const k = parseInt(kSlider.value);

        if (earthquakesData.length < 3) {
            alert('Minimum 3 séismes requis');
            return;
        }

        if (k > earthquakesData.length) {
            alert(`K (${k}) ne peut pas dépasser le nombre de séismes (${earthquakesData.length})`);
            return;
        }

        try {
            applyBtn.disabled = true;
            applyBtn.textContent = ' Calcul...';

            // Forcer un clustering complet
            const res = await fetch(`/kmeans/cluster?k=${k}&force_full=true`);
            const data = await res.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            currentClusteringActive = true;
            currentK = k;  // Enregistrer le K actuel
            lastEarthquakeCount = data.total_earthquakes;

            displayEarthquakes(data.earthquakes, true);
            displayCentroids(data.centers);
            displayClusters(data.clusters);

            totalCount.textContent = data.total_earthquakes;
            clusterCount.textContent = data.n_clusters;

            console.log(` Clustering complet appliqué: ${data.n_clusters} clusters`);

        } catch (err) {
            console.error(" Erreur:", err);
        } finally {
            applyBtn.disabled = false;
            applyBtn.textContent = ' Appliquer le clustering';
        }
    }

    // Reset : supprime TOUT
    function reset() {
        currentClusteringActive = false;
        incrementalMode = false;
        incrementalToggle.checked = false;
        
        //  ARRÊTER LE LONG POLLING
        stopLongPolling();
        
        updateToggleStatus();
        
        displayEarthquakes(earthquakesData);
        centroidsLayer.clearLayers();
        clustersContainer.innerHTML = '<p class="info-message">Appliquez le clustering pour voir les résultats</p>';
        clusterCount.textContent = 0;
        console.log(' Reset effectué');
    }

    // Events
    applyBtn.addEventListener('click', applyClustering);
    resetBtn.addEventListener('click', reset);

    // Initialisation
    loadData();
    
    setInterval(loadData, 20000);
});
