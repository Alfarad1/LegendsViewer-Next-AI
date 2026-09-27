<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue';
import { useBookmarkStore } from '../stores/bookmarkStore';
import {
  checkAiHealth,
  streamChat,
  type ChatHistoryMessage,
  type EntityLink,
} from '../aiClient';

interface UiMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  links: EntityLink[];
  status?: string;
  error?: boolean;
}

const bookmarkStore = useBookmarkStore();
const messages = ref<UiMessage[]>([]);
const input = ref('');
const sending = ref(false);
const aiOnline = ref<boolean | null>(null);
const messagesEl = ref<HTMLElement | null>(null);
let nextId = 1;
let abortController: AbortController | null = null;

const scrollToBottom = async () => {
  await nextTick();
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  }
};

const refreshHealth = async () => {
  aiOnline.value = await checkAiHealth();
};

onMounted(() => {
  refreshHealth();
});

onUnmounted(() => {
  abortController?.abort();
});

const buildHistory = (): ChatHistoryMessage[] =>
  messages.value
    .filter((m) => !m.error && m.content.trim().length > 0)
    .map((m) => ({ role: m.role, content: m.content }));

const send = async () => {
  const text = input.value.trim();
  if (!text || sending.value) {
    return;
  }

  const history = buildHistory();
  messages.value.push({
    id: nextId++,
    role: 'user',
    content: text,
    links: [],
  });
  input.value = '';

  const assistant: UiMessage = {
    id: nextId++,
    role: 'assistant',
    content: '',
    links: [],
    status: 'Thinking…',
  };
  messages.value.push(assistant);
  sending.value = true;
  await scrollToBottom();

  abortController = new AbortController();

  try {
    await streamChat(
      text,
      history,
      (event) => {
        if (event.event === 'status') {
          assistant.status = `Using ${event.data.tool}…`;
        } else if (event.event === 'token') {
          assistant.status = undefined;
          assistant.content += event.data.text;
        } else if (event.event === 'done') {
          assistant.status = undefined;
          assistant.links = event.data.links ?? [];
        } else if (event.event === 'error') {
          assistant.status = undefined;
          assistant.error = true;
          assistant.content = event.data.message || 'AI request failed.';
        }
        void scrollToBottom();
      },
      abortController.signal,
    );

    if (!assistant.content && !assistant.error) {
      assistant.content = 'No response from the assistant.';
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      assistant.content = assistant.content || 'Cancelled.';
    } else {
      assistant.error = true;
      assistant.content = (err as Error).message || 'Failed to reach the AI service.';
      aiOnline.value = false;
    }
  } finally {
    assistant.status = undefined;
    sending.value = false;
    abortController = null;
    await scrollToBottom();
  }
};

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    void send();
  }
};
</script>

<template>
  <div class="chat-page">
    <div class="chat-header">
      <h2 class="text-h5 mb-1">AI Chat</h2>
      <p class="text-body-2 text-medium-emphasis mb-0">
        Ask for a summary of a Site, Historical Figure, or Entity from the loaded world.
      </p>
      <div class="mt-3 d-flex align-center ga-3 flex-wrap">
        <v-chip
          size="small"
          :color="aiOnline === true ? 'success' : aiOnline === false ? 'error' : 'default'"
          variant="tonal"
        >
          AI service: {{ aiOnline === null ? 'checking…' : aiOnline ? 'online' : 'offline' }}
        </v-chip>
        <v-chip
          size="small"
          :color="bookmarkStore.isLoaded ? 'success' : 'warning'"
          variant="tonal"
        >
          World: {{ bookmarkStore.isLoaded ? 'loaded' : 'not loaded' }}
        </v-chip>
        <v-btn size="small" variant="text" @click="refreshHealth">Refresh status</v-btn>
      </div>
    </div>

    <v-alert
      v-if="!bookmarkStore.isLoaded"
      class="mt-4"
      type="warning"
      variant="tonal"
      density="comfortable"
    >
      Load a legends world on Explore Worlds before asking about objects.
    </v-alert>

    <div ref="messagesEl" class="chat-messages mt-4">
      <div v-if="messages.length === 0" class="chat-empty text-medium-emphasis">
        Example: “Tell me about the mountainhome” or “Расскажи про Urist”
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        class="chat-bubble"
        :class="msg.role === 'user' ? 'chat-bubble--user' : 'chat-bubble--assistant'"
      >
        <div class="chat-bubble__role">{{ msg.role === 'user' ? 'You' : 'Assistant' }}</div>
        <div class="chat-bubble__body" :class="{ 'text-error': msg.error }">
          <pre class="chat-text">{{ msg.content || (msg.status ?? '') }}</pre>
          <div v-if="msg.status && msg.content" class="text-caption text-medium-emphasis mt-1">
            {{ msg.status }}
          </div>
        </div>
        <div v-if="msg.links.length" class="chat-links mt-2 d-flex flex-wrap ga-2">
          <v-chip
            v-for="link in msg.links"
            :key="`${link.type}-${link.id}`"
            :to="link.route"
            size="small"
            color="primary"
            variant="outlined"
            prepend-icon="mdi-open-in-new"
          >
            {{ link.name || `${link.type} #${link.id}` }}
          </v-chip>
        </div>
      </div>
    </div>

    <div class="chat-input mt-4">
      <v-textarea
        v-model="input"
        label="Ask about a site, figure, or entity"
        rows="2"
        auto-grow
        max-rows="6"
        variant="outlined"
        hide-details
        :disabled="sending"
        @keydown="onKeydown"
      />
      <v-btn
        class="mt-3"
        color="primary"
        :loading="sending"
        :disabled="!input.trim() || sending"
        prepend-icon="mdi-send"
        @click="send"
      >
        Send
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.chat-page {
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 120px);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  max-height: calc(100vh - 320px);
  min-height: 280px;
}

.chat-empty {
  padding: 24px 8px;
}

.chat-bubble {
  margin-bottom: 16px;
  max-width: 900px;
}

.chat-bubble--user {
  margin-left: auto;
  text-align: right;
}

.chat-bubble--user .chat-bubble__body {
  display: inline-block;
  text-align: left;
  background: rgba(var(--v-theme-primary), 0.12);
  border-radius: 12px;
  padding: 10px 14px;
}

.chat-bubble--assistant .chat-bubble__body {
  background: rgba(var(--v-theme-surface-variant), 0.35);
  border-radius: 12px;
  padding: 10px 14px;
}

.chat-bubble__role {
  font-size: 12px;
  opacity: 0.7;
  margin-bottom: 4px;
}

.chat-text {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 0.95rem;
  line-height: 1.45;
}
</style>
