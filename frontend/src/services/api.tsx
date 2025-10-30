// API service for backend communication
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface SearchFilesRequest {
    user_id: string;
    query: string;
    top_k: number;
    filters?: Record<string, any> | null;
}

interface SearchFilesResponse {
    query_id: number;
    latency_ms: number;
    hits: Array<{
        path?: string;
        title?: string;
        text?: string;
        content?: string;
        score?: number;
        [key: string]: any;
    }>;
    answer?: string;  // Added
    answer_sources?: {  // Added
        local_files?: string[];
        web_urls?: string[];
    };
}

interface WebSearchResponse {
    engine: string;
    attempted_engines: string[];
    q: string;
    data: boolean;
    top_n: number;
    results: Array<{
        title?: string;
        url?: string;
        snippet?: string;
        text?: string;
        text_length?: number;
        source?: string;
        publishedDate?: string;
        scrape_status?: number;
        scrape_error?: string;
    }>;
    event_id: number;
    attempt_errors: Array<{
        engine: string;
        error: string;
    }>;
    answer?: string;  // Added
    answer_sources?: {  // Added
        local_files?: string[];
        web_urls?: string[];
    };
}

interface IndexResponse {
    roots: string[];
    stats: Record<string, any>;
    errors: any[];
    scanned_files: string[];
    changed_files: string[];
    unchanged_files: string[];
    event_id: number;
    latency_ms: number;
}

interface AskWithFileResponse {
    answer: string;
    answer_sources?: {  // Added
        local_files?: string[];
        web_urls?: string[];
    };
    file: {
        original_name: string;
        saved_path: string;
    };
    query: string;
    local: {
        hits: any[];
        error: string | null;
    };
    web: {
        engine_used: string | null;
        results: any[];
        attempt_errors: any[];
    };
    latency_ms: number;
    event_id: number;
    query_id: number | null;
}

class ApiService {
    // File search
    async searchFiles(
        userId: string,
        query: string,
        topK: number = 3,
        filters: Record<string, any> | null = null
    ): Promise<SearchFilesResponse> {
        const response = await fetch(`${API_BASE_URL}/api/v1/file/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_id: userId,
                query: query,
                top_k: topK,
                filters: filters,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail?.message || 'Search failed');
        }

        return response.json();
    }

    // Web search
    async searchWeb(
        query: string,
        engine: string = 'exa',
        data: boolean = false,
        topN: number = 3,
        userId: string = 'anonymous'
    ): Promise<WebSearchResponse> {
        const params = new URLSearchParams({
            engine: engine,
            q: query,
            data: data.toString(),
            top_n: topN.toString(),
            user_id: userId,
        });

        const response = await fetch(`${API_BASE_URL}/api/v1/web/search?${params}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail?.message || 'Web search failed');
        }

        return response.json();
    }

    // Ask with file (Hybrid mode) - upload file and search both local + web
    async askWithFile(
        file: File,
        query: string,
        userId: string = 'anonymous',
        engine: string = 'exa|serper',
        localTopK: number = 3,
        webTopN: number = 3,
        scrapeWeb: boolean = false,
        restrictLocalToFile: boolean = true
    ): Promise<AskWithFileResponse> {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('query', query);
        formData.append('user_id', userId);
        formData.append('engine', engine);
        formData.append('local_top_k', localTopK.toString());
        formData.append('web_top_n', webTopN.toString());
        formData.append('scrape_web', scrapeWeb.toString());
        formData.append('restrict_local_to_file', restrictLocalToFile.toString());

        const response = await fetch(`${API_BASE_URL}/api/v1/ask-with-file`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail?.message || error.detail || 'Ask with file failed');
        }

        return response.json();
    }

    // Index files (incremental)
    async indexFiles(
        roots: string[] | null = null,
        forceReembed: boolean = false,
        model: string | null = null
    ): Promise<IndexResponse> {
        const response = await fetch(`${API_BASE_URL}/api/v1/index`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                roots: roots,
                force_reembed: forceReembed,
                model: model,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Indexing failed');
        }

        return response.json();
    }

    // Index files (full reset)
    async indexFilesFull(
        roots: string[] | null = null,
        model: string | null = null
    ): Promise<IndexResponse> {
        const response = await fetch(`${API_BASE_URL}/api/v1/index-full`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                roots: roots,
                model: model,
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Full indexing failed');
        }

        return response.json();
    }

    async uploadFile(formData: FormData) {
        return fetch(`${API_BASE_URL}/api/v1/upload-file`, {
            method: 'POST',
            body: formData,
        }).then(r => r.json());
    }

    async uploadFiles(files: File[]) {
        const formData = new FormData();
        for (const file of files) {
            formData.append("files", file); // key must match backend argument!
        }
        const res = await fetch(`${API_BASE_URL}/api/v1/upload-files`, {
            method: "POST",
            body: formData
        });
        return res.json();
    }
}

export default new ApiService();