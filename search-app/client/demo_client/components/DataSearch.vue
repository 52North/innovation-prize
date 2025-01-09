<template>
  <div class="metadata-search d-flex flex-column p-3">
    <input type="text" class="form-control mb-3" v-model="searchQuery" @keyup.enter="searchMetadata"
      placeholder="Search for metadata..." />
    <button class="btn btn-primary mb-3" @click="searchMetadata">Search</button>
    <div class="results-container" :class="{ expanded: searchResults.length > 0 }">
      <div v-if="searchResults.length > 0">
        <h4>Search Results:</h4>
        <div class="results">
          <div v-for="(item, index) in searchResults" :key="index" class="result-item p-2 mb-2 border rounded">
            <h5>{{ item.metadata.title }}</h5>
            <p>{{ extractDescription(item.page_content) }}</p>
            <p v-if="extractBBox(item.metadata.extent)">Bounding Box: {{ extractBBox(item.metadata.extent).join(', ') }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import config from '../config';
import axios from 'axios';

export default {
  data() {
    return {
      searchQuery: '',
      searchResults: []
    };
  },
  methods: {
    async searchMetadata() {
      if (this.searchQuery.trim() !== '') {
        try {
          const response = await axios.post(`${config.BACKEND_API_URL}/retrieve_pygeoapi/invoke`, {
            input: this.searchQuery
          });

          if (response.data && response.data.output) {
            this.searchResults = response.data.output;
            const boundingBoxes = this.searchResults.map(item => this.extractBBox(item.metadata.extent)).filter(bbox => bbox);
            this.$emit('update-bounding-boxes', boundingBoxes);
          } else {
            this.searchResults = [];
            console.error('No results found');

          }
        } catch (error) {
          console.error('Error fetching metadata from API:', error);
          this.searchResults = [];
        }
      }
    },
    extractDescription(pageContent) {
      const regex = /Description:\s*(.*?)\s*Keywords:/;
      const match = pageContent.match(regex);
      return match ? match[1] : 'No description available';
    },
    extractBBox(extentStr) {
      try {
        // Replace single quotes with double quotes and None with null
        const jsonString = extentStr.replace(/'/g, '"').replace(/None/g, 'null');
        const extent = JSON.parse(jsonString);
        if (extent.spatial && extent.spatial.bbox) {
          return extent.spatial.bbox[0];
        }
        return null;
      } catch (error) {
        console.error('Error parsing extent:', error);
        return null;
      }
    }
  }
};
</script>

<style scoped>
.form-control {
  border-radius: 30px;
}

.btn {
  margin-left: 1%;
  border-radius: 30px;
}

.metadata-search {
  max-width: 800px;
  margin: 0 auto;
  border: 1px solid #ccc;
  border-radius: 30px;
}

.results-container {
  max-height: 100px;
  overflow: hidden;
  transition: max-height 0.5s ease-in-out;
}

.results-container.expanded {
  max-height: 500px;
  /* Adjust to the desired height */
}


.results {
  max-height: 400px;
  overflow-y: auto;
}

.result-item {
  background-color: #f8f9fa;
}
</style>
  