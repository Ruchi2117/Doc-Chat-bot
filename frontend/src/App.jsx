import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { CircularProgress, Snackbar, Alert, Button } from '@mui/material';
import './App.css';

// API configuration
const API_CONFIG = {
  baseURL: (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, ''),
  timeout: 60000, // 60 second timeout
};

const api = axios.create(API_CONFIG);
const SESSION_STORAGE_KEY = 'doc-chatbot-session-id';

const createSessionId = () => {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const getSessionId = () => {
  const existingSessionId = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (existingSessionId) {
    return existingSessionId;
  }

  const nextSessionId = createSessionId();
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
  return nextSessionId;
};

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isConnected, setIsConnected] = useState(true);
  const [useCaching, setUseCaching] = useState(true);
  const [uploadStatus, setUploadStatus] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [sessionId, setSessionId] = useState(getSessionId);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  
  // Check backend connection
  useEffect(() => {
    const checkBackendConnection = async () => {
      try {
        const response = await api.get('/health');
        setIsConnected(response.data.status === 'ok');
        setError(null);
      } catch (err) {
        setIsConnected(false);
        setError('Cannot connect to the backend server. Please make sure it is running.');
      }
    };

    // Check immediately and then every 30 seconds
    checkBackendConnection();
    const interval = setInterval(checkBackendConnection, 30000);
    return () => clearInterval(interval);
  }, []);
  
  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Clear error after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Prepare conversation history
    // The current messages state (prev inside setMessages) will include the latest userMessage
    const currentMessages = [...messages, userMessage]; // Add current user message to history context
    const historyToSend = currentMessages
      .slice(-6) // Get last 6 messages (3 turns)
      .map(({ role, content }) => ({ role, content })); // Keep only role and content

    try {
      // Create a new message placeholder for the assistant's response
      const assistantMessage = {
        role: 'assistant',
        content: '',
        metadata: [],
        scores: [],
        isStreaming: true
      };
      setMessages(prev => [...prev, assistantMessage]);

      await api.post('/ask', {
        question: userMessage.content, // Send the content of the userMessage object
        use_cache: useCaching,
        history: historyToSend, // Add the conversation history
        session_id: sessionId
      }, {
        responseType: 'text',
        headers: {
          'Accept': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        onDownloadProgress: (progressEvent) => {
          const text = progressEvent.event.target.responseText;
          const lines = text.split('\n');
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') {
                setIsLoading(false);
                continue;
              }
              
              try {
                const parsedData = JSON.parse(data);
                if (parsedData.error) {
                  setMessages(prev => [
                    ...prev.slice(0, -1),
                    { role: 'assistant', content: `Error: ${parsedData.error}`, isError: true }
                  ]);
                  setIsLoading(false);
                  return;
                }

                setMessages(prev => {
                  const newMessages = [...prev];
                  const lastMessage = newMessages[newMessages.length - 1];
                  
                  if (lastMessage.role === 'assistant') {
                    // Check if this chunk is already in the content to avoid duplication
                    if (!lastMessage.content.includes(parsedData.chunk)) {
                      lastMessage.content = parsedData.chunk;  // Replace instead of append
                      lastMessage.metadata = parsedData.metadata;
                      lastMessage.scores = parsedData.scores;
                      lastMessage.isStreaming = true;
                    }
                  }
                  
                  return newMessages;
                });
              } catch (error) {
                console.error('Failed to parse SSE data:', error);
              }
            }
          }
        }
      });
    } catch (error) {
      console.error('Error:', error);
      setIsLoading(false);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Error: Failed to send message', isError: true }
      ]);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setIsUploading(true);
    setUploadStatus('');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', sessionId);

    try {
      await api.post('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setUploadStatus(`Successfully uploaded and processed: ${file.name}`);
      // Add a system message to show the upload success
      setMessages(prev => [...prev, {
        role: 'system',
        content: `Document uploaded: ${file.name}. You can now ask questions about this document.`,
        isSystem: true
      }]);
    } catch (error) {
      console.error('Upload error:', error);
      setError(error.response?.data?.error || 'Failed to upload file');
      setUploadStatus('Failed to upload file');
    } finally {
      setIsUploading(false);
      // Reset the file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleNewSession = () => {
    const nextSessionId = createSessionId();
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, nextSessionId);
    setSessionId(nextSessionId);
    setMessages([]);
    setInput('');
    setUploadStatus('');
    setError(null);
  };

  return (
    <div className="app theme-pink">
      <header className="chat-header">
        <h1>DOC Chatbot</h1>
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          {isConnected ? 'Connected' : 'Disconnected'}
        </div>
      </header>

      <div className="settings-panel">
        <div className="upload-section">
          <input
            type="file"
            onChange={handleFileUpload}
            accept=".txt,.pdf,.md,.docx"
            ref={fileInputRef}
            style={{ display: 'none' }}
          />
          <Button
            variant="contained"
            onClick={() => fileInputRef.current.click()}
            disabled={isUploading || !isConnected}
            style={{ marginRight: '10px' }}
          >
            {isUploading ? 'Uploading...' : 'Upload Document'}
          </Button>
          {uploadStatus && (
            <span className={uploadStatus.includes('Failed') ? 'error-text' : 'success-text'}>
              {uploadStatus}
            </span>
          )}
        </div>
        <Button
          variant="outlined"
          onClick={handleNewSession}
          disabled={isLoading || isUploading}
          style={{ marginRight: '10px' }}
        >
          New Session
        </Button>
        <label className="cache-toggle">
          <input
            type="checkbox"
            checked={useCaching}
            onChange={(e) => setUseCaching(e.target.checked)}
          />
          {'Enable Response Caching'}
        </label>
      </div>

      <div className="chat-container">
        <div className="messages">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`message ${message.role} ${message.isError ? 'error' : ''} ${message.isSystem ? 'system' : ''}`}
            >
              <div className="message-content">
                {message.content}
                {message.isStreaming && <span className="cursor">|</span>}
              </div>
              {message.role === 'assistant' && message.metadata && message.metadata.length > 0 && (
                <div className="sources">
                  <details>
                    <summary>Sources ({message.metadata.length})</summary>
                    <ul>
                      {message.metadata.map((source, idx) => (
                        <li key={idx}>
                          {source.source}
                          {message.scores && message.scores[idx] && (
                            <span className="score">
                              {(message.scores[idx] * 100).toFixed(1)}% match
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="loading">
              <CircularProgress size={24} />
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <form className="input-form" onSubmit={handleSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask me anything about your documents..."
            disabled={!isConnected || isLoading}
          />
          <button type="submit" disabled={!isConnected || isLoading}>
            {isLoading ? 'Thinking...' : 'Send'}
          </button>
        </form>
      </div>

      <Snackbar
        open={!!error}
        autoHideDuration={5000}
        onClose={() => setError(null)}
      >
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      </Snackbar>
    </div>
  );
}

export default App;
