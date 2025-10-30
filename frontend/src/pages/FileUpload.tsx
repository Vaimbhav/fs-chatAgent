import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, X, FileText, Image as ImageIcon, File, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import apiService from '../services/api'
import './FileUpload.css';

interface FileObject {
    id: number;
    file: File;
    name: string;
    size: number;
    type: string;
    uploaded: boolean;
}

interface IndexingStatus {
    type: 'success' | 'error' | 'loading';
    message: string;
    details?: {
        stats?: Record<string, any>;
        changed_files?: string[];
        unchanged_files?: string[];
        latency_ms?: number;
    };
}

export default function FileUpload() {
    const [files, setFiles] = useState<FileObject[]>([]);
    const [isDragging, setIsDragging] = useState<boolean>(false);
    const [uploadProgress, setUploadProgress] = useState<Record<number, number>>({});
    const [indexingStatus, setIndexingStatus] = useState<IndexingStatus | null>(null);
    const [isIndexing, setIsIndexing] = useState<boolean>(false);
    const [rootPath, setRootPath] = useState<string>('');
    const fileInputRef = useRef<HTMLInputElement>(null);
    const navigate = useNavigate();

    const handleFileSelect = (selectedFiles: FileList) => {
        const newFiles = Array.from(selectedFiles).map(file => ({
            id: Date.now() + Math.random(),
            file,
            name: file.name,
            size: file.size,
            type: file.type,
            uploaded: false
        }));
        setFiles(prev => [...prev, ...newFiles]);
    };

    const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(false);
        handleFileSelect(e.dataTransfer.files);
    };

    const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
        e.preventDefault();
        setIsDragging(true);
    };

    const handleDragLeave = () => {
        setIsDragging(false);
    };

    const removeFile = (id: number) => {
        setFiles(prev => prev.filter(f => f.id !== id));
    };

    const uploadFiles = async () => {
        // Only upload files not yet uploaded
        const filesToUpload = files.filter(f => !f.uploaded).map(f => f.file);
        if (filesToUpload.length === 0) return;

        try {
            await apiService.uploadFiles(filesToUpload); // batch upload!
            setFiles(prev =>
                prev.map(f =>
                    f.uploaded ? f : { ...f, uploaded: true }
                )
            );
        } catch (err) {
            console.log(err);
            alert('Failed to upload files. Please try again.');
            // Optional: handle upload error
        }
    }


    const indexRootPath = async (fullReindex: boolean = false) => {
        if (!rootPath.trim()) {
            alert('Please enter a root path to index');
            return;
        }

        setIsIndexing(true);
        setIndexingStatus({ type: 'loading', message: 'Indexing files...' });

        try {
            const result = fullReindex
                ? await apiService.indexFilesFull([rootPath])
                : await apiService.indexFiles([rootPath], false);

            setIndexingStatus({
                type: 'success',
                message: `Successfully indexed ${result.stats?.total_files || 0} files`,
                details: result
            });
        } catch (error) {
            setIndexingStatus({
                type: 'error',
                message: (error as Error).message,
            });
        } finally {
            setIsIndexing(false);
        }
    };

    const getFileIcon = (type: string): React.ReactElement => {
        if (type.startsWith('image/')) return <ImageIcon className="w-6 h-6" />;
        if (type.startsWith('text/')) return <FileText className="w-6 h-6" />;
        return <File className="w-6 h-6" />;
    };

    const formatFileSize = (bytes: number): string => {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <header className="bg-white border-b border-gray-200 px-6 py-4">
                <div className="max-w-6xl mx-auto flex justify-between items-center">
                    <h1 className="text-2xl font-bold text-gray-800">Upload & Index Files</h1>
                    <button
                        onClick={() => navigate('/chat')}
                        className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition"
                    >
                        Back to Chat
                    </button>
                </div>
            </header>

            <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
                {/* Index Root Path Section */}
                <div className="bg-white rounded-xl border border-gray-200 p-6">
                    <h2 className="text-xl font-semibold text-gray-800 mb-4">Index Local Directory</h2>
                    <p className="text-sm text-gray-600 mb-4">
                        Index files from a local directory path. The backend will scan and embed the files.
                    </p>

                    <div className="flex gap-3 mb-4">
                        <input
                            type="text"
                            value={rootPath}
                            onChange={(e) => setRootPath(e.target.value)}
                            placeholder="/path/to/your/documents"
                            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                            onClick={() => indexRootPath(false)}
                            disabled={isIndexing || !rootPath.trim()}
                            className="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            {isIndexing ? (
                                <>
                                    <RefreshCw className="w-4 h-4 animate-spin" />
                                    Indexing...
                                </>
                            ) : (
                                <>
                                    <Upload className="w-4 h-4" />
                                    Index
                                </>
                            )}
                        </button>
                        <button
                            onClick={() => indexRootPath(true)}
                            disabled={isIndexing || !rootPath.trim()}
                            className="px-6 py-2 bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition disabled:opacity-50 disabled:cursor-not-allowed"
                            title="Full reindex (clears existing data)"
                        >
                            Full Reindex
                        </button>
                    </div>

                    {/* Indexing Status */}
                    {indexingStatus && (
                        <div
                            className={`p-4 rounded-lg flex items-start gap-3 ${indexingStatus.type === 'success'
                                ? 'bg-green-50 border border-green-200'
                                : indexingStatus.type === 'error'
                                    ? 'bg-red-50 border border-red-200'
                                    : 'bg-blue-50 border border-blue-200'
                                }`}
                        >
                            {indexingStatus.type === 'success' && <CheckCircle className="w-5 h-5 text-green-600 mt-0.5" />}
                            {indexingStatus.type === 'error' && <AlertCircle className="w-5 h-5 text-red-600 mt-0.5" />}
                            {indexingStatus.type === 'loading' && <RefreshCw className="w-5 h-5 text-blue-600 mt-0.5 animate-spin" />}

                            <div className="flex-1">
                                <p
                                    className={`font-medium ${indexingStatus.type === 'success'
                                        ? 'text-green-800'
                                        : indexingStatus.type === 'error'
                                            ? 'text-red-800'
                                            : 'text-blue-800'
                                        }`}
                                >
                                    {indexingStatus.message}
                                </p>
                                {indexingStatus.details && (
                                    <div className="mt-2 text-sm text-gray-700">
                                        <p>Changed: {indexingStatus.details.changed_files?.length || 0}</p>
                                        <p>Unchanged: {indexingStatus.details.unchanged_files?.length || 0}</p>
                                        <p>Latency: {indexingStatus.details.latency_ms}ms</p>
                                    </div>
                                )}
                            </div>

                            <button
                                onClick={() => setIndexingStatus(null)}
                                className="text-gray-500 hover:text-gray-700"
                                title="Dismiss status"
                                aria-label="Dismiss status"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                    )}
                </div>

                {/* Drop Zone for File Upload (Future Feature) */}
                <div
                    onDrop={handleDrop}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    className={`border-2 border-dashed rounded-xl p-12 text-center transition ${isDragging
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-300 bg-white'
                        }`}
                >
                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={(e) => e.target.files && handleFileSelect(e.target.files)}
                        multiple
                        className="hidden"
                        title="Select files to upload"
                        placeholder="Choose files"
                    />
                    <Upload className={`w-16 h-16 mx-auto mb-4 ${isDragging ? 'text-blue-500' : 'text-gray-400'
                        }`} />
                    <h3 className="text-xl font-semibold text-gray-700 mb-2">
                        Drop files here or click to browse
                    </h3>
                    <p className="text-gray-500 mb-2">
                        Support for images, documents, and text files
                    </p>
                    <p className="text-sm text-gray-400 mb-6">
                        (Note: Direct file upload endpoint coming soon. Use directory indexing for now.)
                    </p>
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        className="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition font-medium"
                    >
                        Select Files
                    </button>
                </div>

                {/* Files List */}
                {files.length > 0 && (
                    <div className="mt-8">
                        <div className="flex justify-between items-center mb-4">
                            <h2 className="text-xl font-semibold text-gray-800">
                                Selected Files ({files.length})
                            </h2>
                            <button
                                onClick={uploadFiles}
                                disabled={files.every(f => f.uploaded)}
                                className="px-6 py-2 bg-green-500 text-white rounded-lg hover:bg-green-600 transition disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                Upload All
                            </button>
                        </div>

                        <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-200">
                            {files.map((fileObj) => (
                                <div key={fileObj.id} className="p-4">
                                    <div className="flex items-center gap-4">
                                        <div className="text-gray-600">
                                            {getFileIcon(fileObj.type)}
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <h3 className="font-medium text-gray-800 truncate">
                                                {fileObj.name}
                                            </h3>
                                            <p className="text-sm text-gray-500">
                                                {formatFileSize(fileObj.size)}
                                            </p>
                                            {uploadProgress[fileObj.id] > 0 && !fileObj.uploaded && (
                                                <div className="mt-2">
                                                    <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                                                        <div
                                                            className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                                                            data-progress={uploadProgress[fileObj.id]}
                                                        ></div>
                                                    </div>
                                                    <p className="text-xs text-gray-500 mt-1">
                                                        {uploadProgress[fileObj.id]}%
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                        {fileObj.uploaded ? (
                                            <CheckCircle className="w-6 h-6 text-green-500" />
                                        ) : (
                                            <button
                                                onClick={() => removeFile(fileObj.id)}
                                                className="text-gray-400 hover:text-red-500 transition"
                                                title="Remove file"
                                            >
                                                <X className="w-6 h-6" />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}