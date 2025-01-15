<template>
  <div class="chatbot-container" :class="{ 'with-artifacts': showArtifacts }">
    <div class="chat-window">
      <div class="messages" ref="messagesContainer">
        <h4><b-icon-chat-left-dots-fill></b-icon-chat-left-dots-fill> Chatbot</h4>
        <div v-for="(message, index) in messages" :key="index" :class="message.type">
          <div v-if="message.type === 'bot'" v-html="markdownToHtml(message.content)"></div>
          <div v-else-if="message.type === 'action-reset'"><button @click="resetSearch" class="btn btn-warning">{{ message.content }}</button></div>
          <div v-else-if="message.type === 'action-search'"><button class="btn btn-info">{{ message.content }}</button></div>
          <div v-else>{{ message.content }}</div>
        </div>
        <div v-if="waitingForResponse" class="feedback-indicator">
          <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden"></span>
          </div>
          <p class="feedback-text">Please wait while we process your request...</p>
        </div>
      </div>
      <div class="input-area">
        <input v-model="userInput" @keyup.enter="sendMessage" placeholder="Type your message...">
        <button @click="sendMessage">Send</button>
      </div>
    </div>
    <transition name="slide">
      <div v-if="showArtifacts" class="artifacts-container">
        <div class="artifacts-header">
            <h3><b-icon-search></b-icon-search>  Search Results:</h3>
          <button @click="toggleArtifacts" class="close-button">&times;</button>
        </div>
        <div class="sticky-map">
          <Map :searchResults="searchResults" :hoveredResultIndex="hoveredResultIndex"
            :zoomedResultIndex="zoomedResultIndex" />
        </div>
        <div class="scrollable-content">
          <div v-if="searchResults.length > 0">
            <b-tabs content-class="mt-2">
              <b-tab title="Results">
                <h4><b-icon-clipboard-data></b-icon-clipboard-data>Result List:</h4>
                <h5>Number of Results: {{ searchResults.length }}</h5>
                <ul>
                  <li v-for="(result, index) in searchResults" :key="index" @mouseover="setHoveredResult(index)"
                    @mouseleave="clearHoveredResult">
                    <a v-if="result.url" :href="result.url" target="_blank">
                      <h5 v-if="apiResponse.index_name == 'geojson'">Feature: {{ result.title }}</h5>
                      <h5 v-else>Dataset: {{ result.title }}</h5>

                    </a>
                    <div v-else>
                      <h5 v-if="apiResponse.index_name == 'geojson'">Feature: {{ result.title }}</h5>
                      <h5 v-else>Dataset: {{ result.title }}</h5>
                    </div>
                    <p>{{ result.description }}</p>
                    <div class="result-links">
                    <div>
                      <button @click="setZoomToFeature(index)" class="btn btn-light">
                        <b-icon-zoom-in></b-icon-zoom-in>
                        Show on map
                      </button>
                    </div>
                
                    <div>
                      <a :href="result.url" class="btn btn-light" target="_blank">
                        <b-icon-arrow-right-circle></b-icon-arrow-right-circle>
                        Go to source</a>
                    </div>
                  </div>
                      <!--
                  <div class="keywords">
                    <strong>Keywords:</strong>
                    <span v-for="(keyword, kIndex) in result.keywords" :key="kIndex" class="badge badge-pill badge-warning">
                      {{ keyword }}
                    </span>
                  </div>
                  -->
                  </li>
                </ul>
              </b-tab>

              <b-tab title="Raw Response">
                <h4>API Response</h4>
                <div class="json-display">
                  <vue-json-pretty :data="apiResponse" :deep="3"></vue-json-pretty>
                </div>
              </b-tab>
            </b-tabs>
          </div>
        </div>
      </div>
    </transition>
    <div class="menu-toggle-wrap">
      <button class="menu-toggle" v-if="!showArtifacts" @click="toggleArtifacts">
        <span class="material-icons">keyboard_double_arrow_right</span>
      </button>
    </div>
  </div>
</template>


<script>
import axios from 'axios';
import Map from './Map.vue';
import config from '../config';
import VueJsonPretty from 'vue-json-pretty';
import 'vue-json-pretty/lib/styles.css';
import { marked } from 'marked';
import jsonData from '../sample_request.json'
import {
  BIconBatteryFull,
  BIconArrow90degDown,
  BIconBookmark,
} from "bootstrap-icons-vue";

export default {
  components: {
    Map,
    VueJsonPretty,
    BIconBatteryFull,
    BIconArrow90degDown,
    BIconBookmark
  },
  data() {
    return {
      messages: [],
      userInput: '',
      showArtifacts: false,
      narrower_terms: "",
      broader_terms: "",
      searchResults: [],
      apiError: false,
      waitingForResponse: false,
      apiResponse: null,
      hoveredResultIndex: null,
      zoomedResultIndex: null,
      jsonData
    };
  },
  methods: {
    async sendMessage() {
      if (!this.userInput.trim()) return;
      
      if (this.userInput === 'reset') {
        this.messages.push({ type: 'user', content: "Resetting chat history"});
      } else {
        this.messages.push({ type: 'user', content: this.userInput });
      }
    
      
      this.waitingForResponse = true;

      try {
        
        console.log(this.userInput);
        const response = await axios.post(`${config.BACKEND_API_URL}/data`, { query: this.userInput }, {
          withCredentials: true
        });

        console.log("Response:", response.data);
         
        // Store the entire response data
        this.apiResponse = response.data;

             // Extract messages from the response
        const messages = response.data.messages;
       
        
        //
        /*
        const response = jsonData;

        console.log("Response:", response);

        this.apiResponse = response;
        const messages = this.apiResponse.messages;
       */
        //
       
   

        if (messages && messages.length > 0) {
          // Extract the latest AI message
          const latestAiMessage = messages.filter(msg => msg.type === 'ai').pop();

          if (latestAiMessage) {
            const messageContent = latestAiMessage.content;
            console.log('Latest AI message content:', messageContent);
            this.messages.push({ type: 'bot', content: messageContent });
          } else {
            console.log('No AI message found');
          }
        } else {
          console.log('No messages found');
        }


        if (this.apiResponse.messages) {
          this.showArtifacts = true;
          /*
          if (response.data.output.search_results && response.data.output.search_results.length > 0) {
            this.searchResults = response.data.output.search_results.map(doc => {
              const extent = this.parseExtent(doc.metadata.extent);
              return {
                title: doc.metadata.title,
                description: this.parseDescription(doc.page_content),
                keywords: this.extractKeywords(doc.page_content),
                url: doc.metadata.url,
                extent: extent
              };
            });
          }*/
          /*
          if (this.apiResponse.search_criteria){
              // Extract entries
            const values = Object.values(this.apiResponse.search_criteria);
            const search_index = this.apiResponse.index_name;
            const search_info = "Search criteria: " +  values + "\n" + "Used search index: " + search_index;
            const _url = 'http://localhost:8000/retrieve_' + search_index + '/invoke'
            const alternative_search = await axios.post(_url, {
              input: search_info
            });
            const alternative_count = alternative_search.data.output.length;
            this.messages.push({ type: 'bot', content: "Searching with '" + values + "' would retrieve at least "+ alternative_count + " results"});
          }
          */
          if (this.apiResponse.search_results && this.apiResponse.search_results.length > 0) {
            this.messages.push({ type: 'action-reset', content: "Start a new search" });
            
            const { narrower_terms, broader_terms } = this.apiResponse;

            this.narrower_terms = narrower_terms;
            this.broader_terms = broader_terms;

            if (narrower_terms && narrower_terms !== 'None') {
              this.messages.push({ 
                type: 'action-search', 
                content: `Search with narrower search terms: '${narrower_terms}'` 
              });
            }

            if (broader_terms && broader_terms !== 'None') {
              this.messages.push({ 
                type: 'action-search', 
                content: `Search with broader search terms: '${broader_terms}'` 
              });
            }

            this.searchResults = this.apiResponse.search_results.map(doc => {
              const spatialExtent = doc.metadata.extent 
                ? this.calcExtentsFromBboxes(doc.metadata.extent.spatial.bbox)
                : this.calcExtentsFromGeoJson(doc.metadata.feature);
              const bboxes = Array.isArray(spatialExtent) ? spatialExtent : [ spatialExtent ]
              console.log("Extent: " + bboxes);
              const item = {
                title: doc.metadata.title || doc.metadata.name,
                description: this.parseDescription(doc.page_content),
                //keywords: this.extractKeywords(doc.page_content),
                bboxes: bboxes
              };
              if (doc.metadata.url) {
                item.url = doc.metadata.url;
              }
              return item;
            });
          }
        }
        this.apiError = false;
      } catch (error) {
        console.error('Error:', error);
        // this.messages.push({ type: 'bot', content: 'Sorry, an error occurred.' });
        this.apiError = true;
      } finally {
        this.waitingForResponse = false;
      }

      this.userInput = '';
      this.$nextTick(() => this.scrollToBottom());
    },
    resetSearch() {
      this.userInput = "reset";
      this.sendMessage();
    },
    markdownToHtml(markdown) {
      return marked(markdown);
    },
    parseDescription(pageContent) {
      const regex = /description:\s*(.*?)(?=\s*\w+:|$)/;
      const match = regex.exec(pageContent);
      return match ? match[1] : 'No description available';
    },
    extractKeywords(pageContent) {
      const regex = /Keywords:\s*\[(.*?)\]/;
      const match = regex.exec(pageContent);
      return match ? match[1].split(',').map(keyword => keyword.trim().slice(1, -1)) : [];
    },
    calcExtentsFromBboxes(bboxes) {
      const extents = []
      for (let i = 0; i < bboxes.length; i++) {
        const bbox = bboxes[i];
        const minLat = bbox[0];
        const minLon = bbox[1];
        const maxLat = bbox[2];
        const maxLon = bbox[3];
        extents.push([[minLon, minLat], [ maxLon, maxLat]]);
      }
      return extents;
    },
    calcExtentsFromGeoJson(geoJsonStr) {
      const geoJson = JSON.parse(geoJsonStr);

      if (geoJson.type !== 'Polygon' || !geoJson.coordinates || geoJson.coordinates.length === 0) {
        throw new Error('Invalid GeoJSON Polygon');
      }
      // Extract the coordinates
      const coordinates = geoJson.coordinates[0]; // Assuming the first ring is the polygon outline

      // Initialize bounding box values
      let minLat = Infinity, maxLat = -Infinity;
      let minLng = Infinity, maxLng = -Infinity;

      // Iterate over the coordinates to find min/max lat/lng
      coordinates.forEach(coord => {
        const [lng, lat] = coord; // Assuming each coordinate is [longitude, latitude]

        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        if (lng < minLng) minLng = lng;
        if (lng > maxLng) maxLng = lng;
      });

      return [[[minLat, minLng], [maxLat, maxLng]]]; // Leaflet expects [southWest, northEast]
      //return [minLng, minLat, maxLng, maxLat];
    },
    scrollToBottom() {
      const container = this.$refs.messagesContainer;
      container.scrollTop = container.scrollHeight;
    },
    toggleArtifacts() {
      this.showArtifacts = !this.showArtifacts;
    },
    setZoomToFeature(index) {
      this.zoomedResultIndex = index; // Call zoomToFeature on the Map component
    },
    setHoveredResult(index) {
      this.hoveredResultIndex = index;
    },
    clearHoveredResult() {
      this.hoveredResultIndex = null;
    },
  }
};
</script>

<style scoped>
.chatbot-container {
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;
}

.chat-window {
  flex: 1;
  display: flex;
  flex-direction: column;
  transition: flex 0.3s ease-in-out;
}

.with-artifacts .chat-window {
  flex: 0.5;
  /* Adjust this value to control the size of the chat window */
}

.header {
  display: flex;
  justify-content: flex-end;
  padding: 10px;
}

li.data:not(:last-child) {
  margin-bottom: 3px;
}

.feedback-text {
  font-size: 0.8rem;
}
.action-search {
  margin-top: 5px;
}

.menu-toggle-wrap {
  display: flex;
  justify-content: flex-end;

  .menu-toggle {
    background: none;
    border: none;
    cursor: pointer;
    transition: 0.3s ease-in-out;
    transform: rotate(-180deg);

    .material-icons {
      font-size: 2rem;
      color: #007bff;
      /* Adjust the color to match your theme */
      transition: 0.3s ease-out;
    }

    &:hover {
      .material-icons {
        color: #0056b3;
        /* Adjust the hover color to match your theme */
        transform: translateX(0.5rem);
      }
    }
  }
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.input-area {
  display: flex;
  padding: 20px;
  border-top: 1px solid #e0e0e0;
}

.input-area input {
  flex: 1;
  padding: 10px;
  font-size: 16px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.input-area button {
  margin-left: 10px;
  padding: 10px 20px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.artifacts-container {
  flex: 0.5;
  display: flex;
  flex-direction: column;
  height: 100vh;
  background-color: #f8f9fa;
  box-shadow: -2px 0 5px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.artifacts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 20px;
  margin-left: 20px;
}

.sticky-map {
  position: sticky;
  top: 0;
  z-index: 1000;
  background-color: #f8f9fa;
  padding: 10px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
}

.scrollable-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}


.close-button {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
}

.user,
.bot {
  margin-bottom: 15px;
  padding: 10px;
  border-radius: 8px;
  max-width: 80%;
}

.user {
  background-color: #e6f2ff;
  align-self: flex-end;
  margin-left: auto;
}

.bot {
  background-color: #f0f0f0;
  align-self: flex-start;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}

.keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  /* Adjust as needed */
  margin-top: 0.5rem;
}

ul li {
  margin-bottom: 20px !important;
  /* Use !important to ensure it overrides other styles if needed */
}

.json-display {
  margin-top: 20px;
}

.artifacts-container .map-container {
  margin-bottom: 20px;
}

.result-links{
  display: inline-flex;
}
</style>
