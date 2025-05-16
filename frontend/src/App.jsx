import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { CircularProgress, Snackbar, Alert, Button } from '@mui/material';
import './App.css';

// API configuration
const API_CONFIG = {
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 60000, // 60 second timeout
};

const api = axios.create(API_CONFIG);

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isConnected, setIsConnected] = useState(true);
  const [useCaching, setUseCaching] = useState(true);
  const [uploadStatus, setUploadStatus] = useState('');
  const [isUploading, setIsUploading] = useState(false);
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
        setError('Cannot connect to backend server. Please make sure it is running.');
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

      const response = await api.post('/ask', {
        question: input,
        use_cache: useCaching
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

    try {
      const response = await api.post('/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setUploadStatus(`Successfully uploaded and processed: ${file.name}`);
      // Add a system message to show the upload success
      setMessages(prev => [...prev, {
        role: 'system',
        content: `📓 Document uploaded: ${file.name}. You can now ask questions about this document.`,
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

  const formatTimestamp = (timestamp) => {
    return new Intl.DateTimeFormat('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    }).format(timestamp);
  };
  
  return (
    <div className="app-container">
      {/* Decorative floating hearts */}
      <div className="floating-heart" style={{ content: "🎓" }}>🎓</div>
      <div className="floating-heart" style={{ content: "📄" }}>📄</div>
      <div className="floating-heart" style={{ content: "📓" }}>📓</div>

      <div className="chat-header">
        <h1> DOC Chatbot </h1>
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          {isConnected ? '🌟 Connected' : '💫 Disconnected'}
        </div>
      </div>

      <div className="settings-panel">
        <div className="upload-section">
          <input
            type="file"
            onChange={handleFileUpload}
            accept=".txt,.pdf,.md,.doc,.docx"
            ref={fileInputRef}
            style={{ display: 'none' }}
          />
          <Button
            variant="contained"
            onClick={() => fileInputRef.current.click()}
            disabled={isUploading || !isConnected}
            style={{ marginRight: '10px' }}
          >
            {isUploading ? '🎓 Uploading...' : '📄 Upload Document'}
          </Button>
          {uploadStatus && (
            <span className={uploadStatus.includes('Failed') ? 'error-text' : 'success-text'}>
              {uploadStatus}
            </span>
          )}
        </div>
        <label className="cache-toggle">
          <input
            type="checkbox"
            checked={useCaching}
            onChange={(e) => setUseCaching(e.target.checked)}
          />
          🔭 Enable Response Caching
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
                {message.isStreaming && <span className="cursor">✨</span>}
              </div>
              {message.role === 'assistant' && message.metadata && message.metadata.length > 0 && (
                <div className="sources">
                  <details>
                    <summary>🔍 Sources ({message.metadata.length})</summary>
                    <ul>
                      {message.metadata.map((source, idx) => (
                        <li key={idx}>
                          📄 {source.source}
                          {message.scores && message.scores[idx] && (
                            <span className="score">
                              ⭐ {(message.scores[idx] * 100).toFixed(1)}% match
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
          <div ref={messagesEndRef} />
        </div>

        <form className="input-form" onSubmit={handleSubmit}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="🔭 Ask me anything..."
            disabled={!isConnected || isLoading}
          />
          <button type="submit" disabled={!isConnected || isLoading}>
            {isLoading ? '🎓 Thinking...' : '💫 Send'}
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
