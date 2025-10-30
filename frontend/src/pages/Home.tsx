import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Send, Paperclip, X, FileText, Image as ImageIcon, Globe, Zap, Sparkles } from 'lucide-react';
import apiService from '../services/api';
import './Home.css';

interface FileInfo {
    name: string;
    size: number;
    type: string;
}

interface Message {
    id: number;
    type: 'user' | 'ai';
    text: string;
    files?: FileInfo[];
    timestamp: Date;
    searchMode?: 'file' | 'web' | 'hybrid';
    results?: any[];
    hits?: any[];
    answer?: string;
    answer_sources?: {
        local_files?: string[];
        web_urls?: string[];
    };
    engine?: string;
    attemptedEngines?: string[];
    hybridData?: {
        answer?: string;
        local?: any;
        web?: any;
        file?: any;
        answer_sources?: {
            local_files?: string[];
            web_urls?: string[];
        };
    };
    isError?: boolean;
}

type SearchMode = 'file' | 'web' | 'hybrid';

export default function Home() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState<string>('');
    const [files, setFiles] = useState<File[]>([]);
    const [isLoading, setIsLoading] = useState<boolean>(false);
    const [searchMode, setSearchMode] = useState<SearchMode>('file');
    const [userId] = useState<string>('user-' + Date.now());
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const navigate = useNavigate();

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
        if (messages.length > 0) {
            const lastMsg = messages[messages.length - 1];
            console.log('Last message:', lastMsg);
            console.log('Last message answer_sources:', lastMsg.answer_sources);
        }
    }, [messages]);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFiles = Array.from(e.target.files || []);
        setFiles(prev => [...prev, ...selectedFiles]);
    };

    const removeFile = (index: number) => {
        setFiles(prev => prev.filter((_, i) => i !== index));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() && files.length === 0) return;

        if (searchMode === 'hybrid' && files.length === 0) {
            alert('Please attach a file for hybrid search mode');
            return;
        }

        const userMessage: Message = {
            id: Date.now(),
            type: 'user',
            text: input,
            files: files.map(f => ({ name: f.name, size: f.size, type: f.type })),
            timestamp: new Date(),
            searchMode
        };

        setMessages(prev => [...prev, userMessage]);
        const queryText = input;
        setInput('');
        const queryFiles = [...files];
        setFiles([]);
        setIsLoading(true);

        try {
            let response;

            if (searchMode === 'web') {
                response = await apiService.searchWeb(
                    queryText,
                    'exa|serper',
                    true,
                    3,
                    userId
                );

                const aiMessage: Message = {
                    id: Date.now() + 1,
                    type: 'ai',
                    text: response.answer || (response.results && response.results.length > 0
                        ? `Found ${response.results.length} results using ${response.engine}`
                        : 'No results found'),
                    answer: response.answer,
                    answer_sources: response.answer_sources ? {
                        local_files: response.answer_sources.local_files || [],
                        web_urls: response.answer_sources.web_urls || []
                    } : undefined,
                    results: response.results || [],
                    engine: response.engine,
                    attemptedEngines: response.attempted_engines || [],
                    searchMode: 'web',
                    timestamp: new Date()
                };

                console.log('=== AI MESSAGE CREATED ===');
                console.log('AI Message:', aiMessage);
                console.log('AI Message answer_sources:', aiMessage.answer_sources);
                console.log('AI Message web_urls:', aiMessage.answer_sources?.web_urls);
                console.log('AI Message stringified:', JSON.stringify(aiMessage, null, 2));

                setMessages(prev => {
                    const newMessages = [...prev, aiMessage];
                    console.log('=== MESSAGES AFTER UPDATE ===', newMessages);
                    return newMessages;
                });

            } else if (searchMode === 'file') {
                response = await apiService.searchFiles(
                    userId,
                    queryText,
                    3,
                    null
                );

                console.log('=== FILE SEARCH RESPONSE ===');
                console.log('Full response:', response);
                console.log('Answer:', response.answer);
                console.log('Answer sources:', response.answer_sources);
                console.log('Local files:', response.answer_sources?.local_files);
                console.log('Response type:', typeof response);
                console.log('Response keys:', Object.keys(response));

                const aiMessage: Message = {
                    id: Date.now() + 1,
                    type: 'ai',
                    text: response.answer || 'Search complete',
                    answer: response.answer,
                    answer_sources: response.answer_sources ? {
                        local_files: response.answer_sources.local_files || [],
                        web_urls: response.answer_sources.web_urls || []
                    } : undefined,
                    hits: response.hits || [],
                    searchMode: 'file',
                    timestamp: new Date()
                };

                console.log('=== FILE SEARCH AI MESSAGE ===');
                console.log('AI Message:', aiMessage);
                console.log('AI Message answer_sources:', aiMessage.answer_sources);
                console.log('AI Message local_files:', aiMessage.answer_sources?.local_files);
                console.log('AI Message stringified:', JSON.stringify(aiMessage, null, 2));

                setMessages(prev => {
                    const newMessages = [...prev, aiMessage];
                    console.log('=== FILE SEARCH MESSAGES AFTER UPDATE ===', newMessages);
                    return newMessages;
                });

            } else if (searchMode === 'hybrid') {
                if (queryFiles.length === 0) {
                    throw new Error('No file provided for hybrid search');
                }

                response = await apiService.askWithFile(
                    queryFiles[0],
                    queryText,
                    userId,
                    'exa|serper',
                    3,
                    3,
                    true,
                    true
                );

                const aiMessage: Message = {
                    id: Date.now() + 1,
                    type: 'ai',
                    text: response.answer || 'Combined search complete',
                    hybridData: {
                        answer: response.answer,
                        local: response.local,
                        web: response.web,
                        file: response.file,
                        answer_sources: response.answer_sources ? {
                            local_files: response.answer_sources.local_files || [],
                            web_urls: response.answer_sources.web_urls || []
                        } : undefined
                    },
                    searchMode: 'hybrid',
                    timestamp: new Date()
                };

                console.log('=== HYBRID AI MESSAGE ===', aiMessage);
                setMessages(prev => [...prev, aiMessage]);
            }
        } catch (error) {
            const errorMessage: Message = {
                id: Date.now() + 1,
                type: 'ai',
                text: `Error: ${(error as Error).message}. Please make sure the backend is running and files are indexed.`,
                isError: true,
                timestamp: new Date()
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const getFileIcon = (type: string): React.ReactElement => {
        if (type.startsWith('image/')) return <ImageIcon className="w-4 h-4" />;
        return <FileText className="w-4 h-4" />;
    };

    const renderResults = (msg: Message): React.ReactElement | null => {
        if (msg.searchMode === 'web' && msg.results) {
            return (
                <div className="mt-3 space-y-3 fade-in">
                    {msg.answer && (
                        <div className="answer-box rounded-xl p-5 mb-3 shadow-lg">
                            <div className="flex items-center gap-2 mb-3">
                                <Sparkles className="w-5 h-5 text-purple-600" />
                                <h4 className="font-bold text-lg text-gray-900">Answer</h4>
                            </div>
                            <p className="text-gray-800 leading-relaxed text-base">{msg.answer}</p>

                            {msg.answer_sources && (msg.answer_sources.local_files?.length || msg.answer_sources.web_urls?.length) ? (
                                <div className="mt-4 pt-4 border-t border-blue-200">
                                    <h5 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                                        <span>📚</span> Sources Used
                                    </h5>

                                    {msg.answer_sources.local_files && msg.answer_sources.local_files.length > 0 && (
                                        <div className="mb-3">
                                            <p className="text-xs text-gray-600 font-semibold mb-2">Local Files:</p>
                                            <div className="space-y-2">
                                                {msg.answer_sources.local_files.map((file, i) => (
                                                    <div key={i} className="text-xs text-gray-700 bg-white/80 rounded-lg px-3 py-2 flex items-center gap-2 shadow-sm hover:shadow-md transition-shadow">
                                                        <span className="text-base">📄</span>
                                                        <span className="truncate font-medium">{file.split('/').pop()}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {msg.answer_sources.web_urls && msg.answer_sources.web_urls.length > 0 && (
                                        <div>
                                            <p className="text-xs text-gray-600 font-semibold mb-2">Web Sources ({msg.answer_sources.web_urls.length}):</p>
                                            <div className="space-y-2">
                                                {msg.answer_sources.web_urls.map((url, i) => (
                                                    <a
                                                        key={i}
                                                        href={url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-xs text-blue-600 hover:text-blue-800 bg-white/80 rounded-lg px-3 py-2 flex items-start gap-2 block shadow-sm hover:shadow-md transition-all"
                                                    >
                                                        <span className="flex-shrink-0 text-base">🌐</span>
                                                        <span className="break-all text-left">{url}</span>
                                                    </a>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : null}
                        </div>
                    )}

                    {msg.engine && (
                        <div className="text-xs text-gray-500 flex items-center gap-2 flex-wrap px-2">
                            <span className="source-badge">
                                🔍 {msg.engine}
                            </span>
                            {msg.attemptedEngines && msg.attemptedEngines.length > 0 && (
                                <span className="text-gray-400">(Attempted: {msg.attemptedEngines.join(', ')})</span>
                            )}
                        </div>
                    )}

                    {msg.results.length > 0 && (
                        <div>
                            <h4 className="font-bold text-gray-800 mb-3 text-sm flex items-center gap-2">
                                <Globe className="w-4 h-4 text-blue-600" />
                                Found {msg.results.length} web result{msg.results.length > 1 ? 's' : ''}
                            </h4>
                            {msg.results.map((result, i) => (
                                <div key={i} className="result-card border border-gray-200 rounded-xl p-4 bg-white hover:bg-gray-50 mb-3 shadow-sm">
                                    <a
                                        href={result.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="font-semibold text-blue-600 hover:text-blue-800 block mb-2 text-base"
                                    >
                                        {result.title || 'Untitled'}
                                    </a>
                                    {result.snippet && (
                                        <p className="text-sm text-gray-700 mb-3 leading-relaxed">{result.snippet}</p>
                                    )}
                                    <div className="flex gap-3 text-xs text-gray-500 flex-wrap">
                                        {result.publishedDate && (
                                            <span className="flex items-center gap-1">
                                                📅 {new Date(result.publishedDate).toLocaleDateString()}
                                            </span>
                                        )}
                                        {result.source && (
                                            <span className="flex items-center gap-1">
                                                📰 {result.source}
                                            </span>
                                        )}
                                        {result.text && (
                                            <span className="flex items-center gap-1">
                                                📝 {result.text_length || result.text.length} chars
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            );
        }

        if (msg.searchMode === 'file') {
            return (
                <div className="mt-3 space-y-3 fade-in">
                    {msg.answer && (
                        <div className="answer-box rounded-xl p-5 mb-3 shadow-lg">
                            <div className="flex items-center gap-2 mb-3">
                                <Sparkles className="w-5 h-5 text-purple-600" />
                                <h4 className="font-bold text-lg text-gray-900">Answer</h4>
                            </div>
                            <p className="text-gray-800 leading-relaxed text-base">{msg.answer}</p>

                            {msg.answer_sources && (msg.answer_sources.local_files?.length || msg.answer_sources.web_urls?.length) ? (
                                <div className="mt-4 pt-4 border-t border-blue-200">
                                    <h5 className="text-sm font-bold text-gray-800 mb-3 flex items-center gap-2">
                                        <span>📚</span> Sources Used
                                    </h5>

                                    {msg.answer_sources.local_files && msg.answer_sources.local_files.length > 0 && (
                                        <div className="mb-3">
                                            <p className="text-xs text-gray-600 font-semibold mb-2">Local Files ({msg.answer_sources.local_files.length}):</p>
                                            <div className="space-y-2">
                                                {msg.answer_sources.local_files.map((file, i) => (
                                                    <div key={i} className="text-xs text-gray-700 bg-white/80 rounded-lg px-3 py-2 flex items-start gap-2 shadow-sm hover:shadow-md transition-shadow">
                                                        <span className="flex-shrink-0 text-base">📄</span>
                                                        <span className="break-all text-left font-medium">{file}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {msg.answer_sources.web_urls && msg.answer_sources.web_urls.length > 0 && (
                                        <div>
                                            <p className="text-xs text-gray-600 font-semibold mb-2">Web Sources ({msg.answer_sources.web_urls.length}):</p>
                                            <div className="space-y-2">
                                                {msg.answer_sources.web_urls.map((url, i) => (
                                                    <a
                                                        key={i}
                                                        href={url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-xs text-blue-600 hover:text-blue-800 bg-white/80 rounded-lg px-3 py-2 flex items-start gap-2 block shadow-sm hover:shadow-md transition-all"
                                                    >
                                                        <span className="flex-shrink-0 text-base">🌐</span>
                                                        <span className="break-all text-left">{url}</span>
                                                    </a>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : null}
                        </div>
                    )}

                    {msg.hits && msg.hits.length > 0 && (
                        <div>
                            <h4 className="font-bold text-gray-800 mb-3 text-sm flex items-center gap-2">
                                <FileText className="w-4 h-4 text-green-600" />
                                Found {msg.hits.length} relevant document{msg.hits.length > 1 ? 's' : ''}
                            </h4>
                            <div className="space-y-3">
                                {msg.hits.map((hit, i) => (
                                    <div key={i} className="result-card border border-gray-200 rounded-xl p-4 bg-white shadow-sm">
                                        {hit.path && (
                                            <div className="font-semibold text-gray-800 text-sm mb-2 flex items-center gap-2">
                                                <FileText className="w-4 h-4 text-blue-600" />
                                                {hit.path}
                                            </div>
                                        )}
                                        <p className="text-sm text-gray-700 leading-relaxed">{hit.text || hit.content}</p>
                                        <p className="text-xs text-gray-500 mt-2 flex items-center gap-1">
                                            <span className="source-badge">
                                                Score: {hit.score?.toFixed(3) || 'N/A'}
                                            </span>
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            );
        }

        if (msg.searchMode === 'hybrid' && msg.hybridData) {
            return (
                <div className="mt-3 space-y-4 fade-in">
                    {msg.hybridData.answer && (
                        <div className="answer-box rounded-xl p-5 shadow-lg" style={{ background: 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)' }}>
                            <h4 className="font-bold text-blue-900 mb-3 flex items-center gap-2 text-lg">
                                <Sparkles className="w-5 h-5" />
                                Correct Answer
                            </h4>
                            <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{msg.hybridData.answer}</p>

                            {msg.hybridData.answer_sources && (msg.hybridData.answer_sources.local_files?.length > 0 || msg.hybridData.answer_sources.web_urls?.length > 0) && (
                                <div className="mt-4 pt-4 border-t border-blue-300">
                                    <h5 className="text-sm font-bold text-blue-900 mb-3 flex items-center gap-2">
                                        <span>📚</span> Sources Used
                                    </h5>

                                    {msg.hybridData.answer_sources.local_files && msg.hybridData.answer_sources.local_files.length > 0 && (
                                        <div className="mb-3">
                                            <p className="text-xs text-blue-700 font-semibold mb-2">Local Files:</p>
                                            <div className="space-y-2">
                                                {msg.hybridData.answer_sources.local_files.map((file, i) => (
                                                    <div key={i} className="text-xs text-gray-700 bg-white/80 rounded-lg px-3 py-2 flex items-center gap-2 shadow-sm hover:shadow-md transition-shadow">
                                                        <span className="text-base">📄</span>
                                                        <span className="truncate font-medium">{file.split('/').pop()}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {msg.hybridData.answer_sources.web_urls && msg.hybridData.answer_sources.web_urls.length > 0 && (
                                        <div>
                                            <p className="text-xs text-blue-700 font-semibold mb-2">Web Sources:</p>
                                            <div className="space-y-2">
                                                {msg.hybridData.answer_sources.web_urls.map((url, i) => (
                                                    <a
                                                        key={i}
                                                        href={url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-xs text-blue-600 hover:text-blue-800 bg-white/80 rounded-lg px-3 py-2 flex items-center gap-2 block shadow-sm hover:shadow-md transition-all"
                                                    >
                                                        <span className="text-base">🌐</span>
                                                        <span className="truncate text-left">{url}</span>
                                                    </a>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {msg.hybridData.file && (
                        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border-2 border-green-200 rounded-xl p-4 shadow-md">
                            <h4 className="font-bold text-green-900 text-sm mb-2 flex items-center gap-2">
                                <FileText className="w-4 h-4" />
                                Uploaded File
                            </h4>
                            <p className="text-xs text-gray-700 font-medium">{msg.hybridData.file.original_name}</p>
                        </div>
                    )}

                    {msg.hybridData.local?.hits && msg.hybridData.local.hits.length > 0 && (
                        <div>
                            <h4 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
                                <FileText className="w-5 h-5 text-green-600" />
                                From Your File ({msg.hybridData.local.hits.length})
                            </h4>
                            <div className="space-y-3">
                                {msg.hybridData.local.hits.slice(0, 3).map((hit: any, i: number) => (
                                    <div key={i} className="result-card border border-gray-200 rounded-xl p-4 bg-white shadow-sm">
                                        <p className="text-sm text-gray-700 leading-relaxed">{hit.text || hit.content}</p>
                                        <p className="text-xs text-gray-500 mt-2">
                                            <span className="source-badge">
                                                Score: {hit.score?.toFixed(3) || 'N/A'}
                                            </span>
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {msg.hybridData.web?.results && msg.hybridData.web.results.length > 0 && (
                        <div>
                            <h4 className="font-bold text-gray-800 mb-3 flex items-center gap-2">
                                <Globe className="w-5 h-5 text-blue-600" />
                                From the Web ({msg.hybridData.web.results.length})
                            </h4>
                            <div className="space-y-3">
                                {msg.hybridData.web.results.slice(0, 3).map((result: any, i: number) => (
                                    <div key={i} className="result-card border border-gray-200 rounded-xl p-4 bg-white shadow-sm">
                                        <a
                                            href={result.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="font-semibold text-blue-600 hover:text-blue-800 text-sm block mb-2"
                                        >
                                            {result.title}
                                        </a>
                                        <p className="text-xs text-gray-600 leading-relaxed">{result.snippet}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            );
        }

        return null;
    };

    const getModeIcon = (mode: SearchMode) => {
        switch (mode) {
            case 'file': return <FileText className="w-4 h-4" />;
            case 'web': return <Globe className="w-4 h-4" />;
            case 'hybrid': return <Zap className="w-4 h-4" />;
        }
    };

    const getModeLabel = (mode: SearchMode) => {
        switch (mode) {
            case 'file': return 'Local Files';
            case 'web': return 'Web Search';
            case 'hybrid': return 'Hybrid';
        }
    };

    return (
        <div className="flex flex-col h-screen gradient-bg">
            {/* Header */}
            <header className="glass-effect border-b border-white/20 px-6 py-4 shadow-lg">
                <div className="max-w-15/16 mx-auto flex justify-between items-center">
                    <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-600 via-pink-600 to-blue-600 bg-clip-text text-transparent flex items-center gap-3">
                        <Sparkles className="w-8 h-8 text-purple-600 float-animation" />
                        ChatBot
                    </h1>
                    <div className="flex gap-3 items-center">
                        {/* Search Mode Toggle - 3 modes */}
                        <div className="flex glass-effect rounded-xl p-1.5 shadow-lg">
                            <button
                                onClick={() => setSearchMode('file')}
                                className={`mode-toggle-btn px-4 py-2 rounded-lg text-sm font-semibold transition-all flex items-center gap-2 ${searchMode === 'file'
                                    ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white shadow-lg scale-105'
                                    : 'text-gray-700 hover:bg-white/50'
                                    }`}
                                title="Search local indexed files"
                            >
                                <FileText className="w-4 h-4" />
                                Files
                            </button>
                            <button
                                onClick={() => setSearchMode('web')}
                                className={`mode-toggle-btn px-4 py-2 rounded-lg text-sm font-semibold transition-all flex items-center gap-2 ${searchMode === 'web'
                                    ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white shadow-lg scale-105'
                                    : 'text-gray-700 hover:bg-white/50'
                                    }`}
                                title="Search the web"
                            >
                                <Globe className="w-4 h-4" />
                                Web
                            </button>
                            <button
                                onClick={() => setSearchMode('hybrid')}
                                className={`mode-toggle-btn px-4 py-2 rounded-lg text-sm font-semibold transition-all flex items-center gap-2 ${searchMode === 'hybrid'
                                    ? 'bg-gradient-to-r from-purple-600 to-blue-600 text-white shadow-lg scale-105'
                                    : 'text-gray-700 hover:bg-white/50'
                                    }`}
                                title="Upload file and search both local + web"
                            >
                                <Zap className="w-4 h-4" />
                                Hybrid
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            {/* Messages Container */}
            <div className="flex-1 overflow-y-auto px-6 py-4 custom-scrollbar">
                <div className="max-w-13/16 mx-auto space-y-4">
                    {messages.length === 0 ? (
                        <div className="text-center text-white mt-20">
                            <div className="empty-state-icon inline-block mb-6">
                                <Sparkles className="w-20 h-20 text-white opacity-80" />
                            </div>
                            <h2 className="text-4xl font-bold mb-4 text-white drop-shadow-lg">How can I help you today?</h2>
                            <p className="text-white/90 text-lg mb-6 drop-shadow">
                                {searchMode === 'file' && '🗂️ Search your local indexed files'}
                                {searchMode === 'web' && '🌐 Search the web for information'}
                                {searchMode === 'hybrid' && '⚡ Upload a file and get answers from both your file and the web'}
                            </p>
                            {searchMode === 'hybrid' && (
                                <div className="mt-8 glass-effect border border-white/30 rounded-2xl p-6 max-w-md mx-auto shadow-2xl">
                                    <p className="text-sm text-black/90 leading-relaxed">
                                        💡 <strong>Hybrid mode:</strong> Attach a file, ask a question, and get insights from both your document and web sources.
                                    </p>
                                </div>
                            )}
                        </div>
                    ) : (
                        messages.map((msg) => (
                            <div
                                key={msg.id}
                                className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'} ${msg.type === 'user' ? 'message-enter-right' : 'message-enter-left'
                                    }`}
                            >
                                <div
                                    className={`max-w-2xl rounded-2xl px-5 py-4 ${msg.type === 'user'
                                        ? 'user-message-gradient text-white'
                                        : msg.isError
                                            ? 'bg-red-100 text-red-800 border-2 border-red-300 shadow-lg'
                                            : 'ai-message-glow glass-effect text-gray-800'
                                        }`}
                                >
                                    <div className="flex items-center gap-2 mb-2">
                                        {msg.searchMode && getModeIcon(msg.searchMode)}
                                        <span className={`text-xs font-semibold ${msg.type === 'user' ? 'text-white/90' : 'text-gray-600'}`}>
                                            {msg.searchMode && getModeLabel(msg.searchMode)}
                                        </span>
                                    </div>
                                    <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                                    {msg.files && msg.files.length > 0 && (
                                        <div className="mt-3 space-y-2">
                                            {msg.files.map((file, i) => (
                                                <div
                                                    key={i}
                                                    className={`flex items-center gap-2 text-sm ${msg.type === 'user' ? 'text-white/90' : 'text-gray-600'
                                                        } bg-white/20 rounded-lg px-3 py-2`}
                                                >
                                                    {getFileIcon(file.type)}
                                                    <span className="truncate font-medium">{file.name}</span>
                                                    <span className="text-xs">({(file.size / 1024).toFixed(1)} KB)</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    {renderResults(msg)}
                                </div>
                            </div>
                        ))
                    )}
                    {isLoading && (
                        <div className="flex justify-start message-enter-left">
                            <div className="glass-effect border border-white/30 rounded-2xl px-5 py-4 shadow-lg">
                                <div className="flex gap-2">
                                    <div className="w-3 h-3 loading-dot rounded-full animate-bounce"></div>
                                    <div className="w-3 h-3 loading-dot rounded-full animate-bounce animation-delay-100"></div>
                                    <div className="w-3 h-3 loading-dot rounded-full animate-bounce animation-delay-200"></div>
                                </div>
                            </div>
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>
            </div>

            {/* Input Area */}
            <div className="glass-effect border-t border-white/20 px-6 py-5 shadow-2xl">
                <div className="max-w-13/16 my-2 mx-auto">
                    {/* File Previews */}
                    {files.length > 0 && (
                        <div className="mb-4 flex flex-wrap gap-3">
                            {files.map((file, index) => (
                                <div
                                    key={index}
                                    className="file-card flex items-center gap-3 rounded-xl px-4 py-3 text-sm shadow-md"
                                >
                                    {getFileIcon(file.type)}
                                    <span className="truncate max-w-xs font-medium text-gray-700">{file.name}</span>
                                    <button
                                        type="button"
                                        onClick={() => removeFile(index)}
                                        className="text-gray-500 hover:text-red-600 transition-colors ml-2"
                                        title="Remove file"
                                        aria-label="Remove file"
                                    >
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Input Form */}
                    <form onSubmit={handleSubmit} className="flex gap-3">
                        {(searchMode === 'hybrid') && (
                            <>
                                <input
                                    type="file"
                                    ref={fileInputRef}
                                    onChange={handleFileSelect}
                                    // multiple={searchMode === 'file'}
                                    className="hidden"
                                    placeholder="Attach file(s)"
                                    title={searchMode === 'hybrid' ? 'Attach file (required for hybrid mode)' : 'Attach files'}
                                />
                                <button
                                    type="button"
                                    onClick={() => fileInputRef.current?.click()}
                                    className="p-4 glass-effect text-purple-600 rounded-xl hover:bg-white/80 transition-all shadow-lg hover:shadow-xl hover:scale-105"
                                    title={searchMode === 'hybrid' ? 'Attach file (required for hybrid mode)' : 'Attach files'}
                                >
                                    <Paperclip className="w-5 h-5" />
                                </button>
                            </>
                        )}
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder={
                                searchMode === 'web'
                                    ? 'Search the web...'
                                    : searchMode === 'hybrid'
                                        ? 'Add a file first, then ask a question ...'
                                        : 'Search your files...'
                            }
                            className="flex-1 px-5 py-4 glass-effect border border-white/30 rounded-xl focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent text-gray-800 placeholder-gray-500 shadow-lg"
                        />
                        <button
                            type="submit"
                            disabled={!input.trim() || (searchMode === 'hybrid' && files.length === 0)}
                            className="shimmer-button p-4 text-white rounded-xl transition-all shadow-lg hover:shadow-2xl disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg hover:scale-105"
                            title="Send message"
                            aria-label="Send message"
                        >
                            <Send className="w-5 h-5" />
                        </button>
                    </form>

                </div>
            </div>
        </div>
    );
}







