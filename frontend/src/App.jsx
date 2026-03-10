import { useState } from "react";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [documentId, setDocumentId] = useState(null);
  const [filename, setFilename] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  async function handleUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setDocumentId(null);
    setFilename(null);
    setMessages([]);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.error) {
        setUploadError(data.error);
      } else {
        setDocumentId(data.document_id);
        setFilename(data.filename);
      }
    } catch (err) {
      setUploadError("Failed to connect to the server. Is the backend running?");
    } finally {
      setUploading(false);
    }
  }

  async function handleAsk(e) {
    e.preventDefault();
    if (!question.trim() || !documentId || asking) return;

    const userMessage = { role: "user", text: question };
    setMessages((prev) => [...prev, userMessage]);
    setQuestion("");
    setAsking(true);

    try {
      const res = await fetch(`${API_BASE}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: documentId, question }),
      });
      const data = await res.json();

      const botMessage = {
        role: "bot",
        text: data.answer || data.error || "No response received.",
      };
      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "Error: Could not reach the server." },
      ]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>PDF Q&A</h1>
        <p>Upload a PDF and ask questions about it</p>
      </header>

      <main className="app-main">
        {/* Upload section */}
        <div className="upload-section">
          <label className={`upload-box ${uploading ? "loading" : ""}`}>
            <input
              type="file"
              accept=".pdf"
              onChange={handleUpload}
              disabled={uploading}
              hidden
            />
            {uploading ? (
              <span>Processing PDF...</span>
            ) : documentId ? (
              <span className="uploaded">✓ {filename}</span>
            ) : (
              <span>Click to upload a PDF</span>
            )}
          </label>

          {uploadError && <p className="error">{uploadError}</p>}
        </div>

        {/* Chat section */}
        {documentId && (
          <div className="chat-section">
            <div className="messages">
              {messages.length === 0 && (
                <p className="placeholder">Ask anything about your document...</p>
              )}
              {messages.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  <span className="bubble">{msg.text}</span>
                </div>
              ))}
              {asking && (
                <div className="message bot">
                  <span className="bubble thinking">Thinking...</span>
                </div>
              )}
            </div>

            <form className="input-row" onSubmit={handleAsk}>
              <input
                type="text"
                placeholder="Ask a question..."
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={asking}
              />
              <button type="submit" disabled={!question.trim() || asking}>
                Ask
              </button>
            </form>
          </div>
        )}
      </main>
    </div>
  );
}
