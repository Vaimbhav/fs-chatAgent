function ErrorPage() {
    return (
        <div className="min-h-screen flex items-center justify-center bg-red-50">
            <div className="text-center">
                <h1 className="text-4xl font-bold text-red-600 mb-4">404</h1>
                <p className="text-xl text-gray-700">Oops! Page not found.</p>
                <a href="/" className="mt-6 inline-block bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600 transition">
                    Go to Home
                </a>
            </div>

        </div>
    );
}

export default ErrorPage;