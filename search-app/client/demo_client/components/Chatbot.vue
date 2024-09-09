<template>
  <div class="chatbot">
    <transition name="fade">
      <div v-if="!showResults" class="messages">
        <div v-for="(message, index) in messages" :key="index" :class="message.sender">
          <div v-if="message.type === 'text'">
            <img v-if="message.sender === 'bot'" src="../assets/ai.jpg" class="message-icon" alt="Bot">
            <img v-else src="../assets/human.jpg" class="message-icon" alt="User">

            {{ message.content }}
          </div>
          <div v-else-if="message.type === 'buttons'" class="button-container">
            <button v-for="button in message.buttons" :key="button.text"
            :class="['btn', button.action === 'Yes' || button.action === 'No' ? 'btn-primary' : 'badge badge-pill badge-info']"
            @click="handleButtonClick(button)">
            {{ button.text }}
            </button>
          </div>
        </div>
      </div>
    </transition>
    <div class="input d-flex p-3 border-top">
      <input type="text" class="form-control me-2" v-model="newMessage" @focus="handleFocus" @keyup.enter="sendMessage"
        placeholder="What data are you interested in..." />
      <button class="btn btn-primary" @click="sendMessage">Send</button>
    </div>
  </div>
</template>


<script>
import axios from 'axios';
import aiURL from '../assets/ai.jpg';
import hunabURL from '../assets/human.jpg';
import jsonData from '../sample_request.json'

export default {
  data() {
    return {
      messages: [],
      newMessage: '',
      facets: {},
      showResults: false,
      searchResults: []
    };
  },
  methods: {
    handleButtonClick(button) {
      if (button.action === 'Yes') {
        this.displayFacetButtons();
      } else if (button.action === 'No') {
        this.emitResults();
      } else {
        this.newMessage = button.action;
        this.sendMessage();
      }
    },
    handleSecondaryAction(button) {
      // Implement secondary button action logic here
      console.log(`Secondary action: ${button.action}`);
    },
    async sendMessage() {
      if (this.newMessage.trim() !== '') {
        this.messages.push({ type: 'text', content: this.newMessage, sender: 'user' });
        const userMessage = this.newMessage;
        this.newMessage = '';

        try {
          /*
          const facetsResponse = await axios.get(`http://localhost:8000/get_related_facets`, {
            params: {
              query: userMessage,
              vocabulary_name: "gemet"
            }
          });
          this.facets = facetsResponse.data;
          console.log("Related terms:", this.facets);

          const response = await axios.post('http://localhost:8000/retrieve_pygeoapi/invoke', {
            input: userMessage
          });

          this.searchResults = response.data.output;
          */
          
          this.searchResults = jsonData;
          console.log("Hello");

          const message = `I found ${response.data.output.length} records for your query. Would you like me to display the results or should we refine the search criteria?`;
          this.messages.push({
            type: 'text',
            content: message,
            sender: 'bot'
          });

          this.messages.push({
            type: 'buttons',
            buttons: [
              { text: 'Refine search', action: 'Yes' },
              { text: 'Show me results based on the current search terms', action: 'No' }
            ],
            sender: 'bot'
          });
        } catch (error) {
          console.error('Error fetching response from API:', error);
          this.messages.push({
            type: 'text',
            content: 'There was an error connecting to the server.',
            sender: 'bot'
          });
        }
      }
    },
    displayFacetButtons() {
      const buttons = [];
      for (const [term, count] of Object.entries(this.facets.broader_terms)) {
        buttons.push({ text: `Broader: ${term} (${count} results)`, action: term });
      }
      for (const [term, count] of Object.entries(this.facets.narrower_terms)) {
        buttons.push({ text: `Narrower: ${term} (${count} results)`, action: term });
      }
      this.messages.push({
        type: 'buttons',
        buttons: buttons,
        sender: 'bot'
      });
    },
    emitResults() {
      this.$emit('results', this.searchResults);
      this.showResults = true;
    },
    hideResults() {
      this.showResults = false;
    },
    handleFocus() {
      this.hideResults();
      this.$emit('focusInput');
    }
  }
};
</script>

<style scoped>
.chatbot {
  height: 100%;
  display: flex;
  flex-direction: column;
  transition: height all 2s ease-out; 
}

.messages {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-radius: 30px;
  transition: all 2s ease-in-out;
}

.user{
  text-align: right;
}

.message-icon {
  width: 30px; /* Adjust the size of the icons */
  height: 30px;
  margin-right: 10px;
  border-radius: 50%; /* Makes the icons circular */
}
.input {
  padding: 1%;
  border-top: 1px solid #ccc;
}

.button-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px; /* Adds space between the buttons */
}

.form-control {
  border-radius: 30px;
}

.btn {
  margin-left: 1%;
  border-radius: 30px;
}

.btn.badge.badge-pill.badge-info{
  size-adjust: 120%;
}

.fade-enter-active, .fade-leave-active {
  transition: 2s ease-in-out;
}


.fade-enter, .fade-leave-to {
  transition: all 0.2s ease-in-out;
  opacity: 1;
}
</style>
