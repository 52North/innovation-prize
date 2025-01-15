<template>
  <div id="map" style="height: 400px; width: 800px;"></div>
</template>

<script>
import { onMounted, onUnmounted, watch, nextTick } from 'vue';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

export default {
  name: 'Map',
  props: {
    searchResults: {
      type: Array,
      default: () => []
    },
    hoveredResultIndex: {
      type: Number,
      default: null
    },
    zoomedResultIndex: {
      type: Number,
      default: null
    }
  },
  setup(props) {
    let map = null;
    let mainLayer = null;
    let fallbackLayer = null;
    let rectangles = [];

    const initMap = () => {
      if (!map) {
        map = L.map('map').setView([0, 0], 2);

        mainLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '© OpenStreetMap contributors'
        }).addTo(map);

        fallbackLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
          maxZoom: 19,
          attribution: 'Tiles © Esri'
        });

        mainLayer.on('tileerror', function (error, tile) {
          console.log('Tile error, switching to fallback layer');
          map.removeLayer(mainLayer);
          fallbackLayer.addTo(map);
        });

        // Invalidate size after map is ready
        nextTick(() => {
          map.invalidateSize();
        });
      }
    };

    const updateMap = () => {
      if (map) {
        // Clear existing rectangles
        rectangles.forEach(rectangle => map.removeLayer(rectangle));
        rectangles = [];

        // Add new rectangles based on search results
        props.searchResults.forEach((result, index) => {
          if (result.bboxes) {
            // hack: only get the first bbox
            const rectangle = L.rectangle(result.bboxes[0], {
              color: "#ff7800",
              weight: 1,
              fillOpacity: 0.01
            }).addTo(map);
            rectangles.push(rectangle);
          }
        });

        // Fit map to show all rectangles
        if (rectangles.length > 0) {
          map.fitBounds(L.featureGroup(rectangles).getBounds());
        } else {
          map.setView([0, 0], 2); // Reset view if no bounds
        }

        // Force a redraw of the map
        nextTick(() => {
          map.invalidateSize();
        });
      }
    };

    const highlightRectangle = (index) => {
      if (rectangles[index]) {
        /*
        map.fitBounds(rectangles[index].getBounds(), {
          padding: [50, 50], // Adjust the padding as needed
          maxZoom: 15 // Optional: set a maximum zoom level to avoid too much zoom
        });
        */
        rectangles[index].setStyle({
          color: "#0000ff",
          weight: 3,
          fillOpacity: 0.4
        });
        rectangles[index].bringToFront();
      }
    };

    const resetRectangleStyle = (index) => {
      if (rectangles[index]) {
        rectangles[index].setStyle({
          color: "#ff7800",
          weight: 1,
          fillOpacity: 0.2
        });
      }
    };

    const zoomToFeature = (index) => {
      if (rectangles[index]) {
        map.fitBounds(rectangles[index].getBounds(), {
          padding: [50, 50],
          maxZoom: 15
        });
      }
    };

    watch(() => props.zoomedResultIndex, (newIndex) => {
      if (newIndex !== null) {
        zoomToFeature(newIndex);
      }
    });

    watch(() => props.hoveredResultIndex, (newIndex, oldIndex) => {
      if (oldIndex !== null) resetRectangleStyle(oldIndex);
      if (newIndex !== null) highlightRectangle(newIndex);
    });
    watch(() => props.searchResults, updateMap, { deep: true });

    onMounted(() => {
      initMap();
      updateMap();
    });

    onUnmounted(() => {
      if (map) {
        map.remove();
      }
    });

    return {
      zoomToFeature
    };
  }
};
</script>

<style scoped>
.leaflet-container{
  width: 100%;
}
</style>