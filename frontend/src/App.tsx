// import { BrowserRouter, Routes, Route } from "react-router-dom";

// import ErrorPage from "./pages/Error";
// import Home from "./pages/Home";
// import FileUpload from "./pages/FileUpload";


// function App() {
//     return (
//         <BrowserRouter>
//             <Routes>
//                 <Route path="/" element={<Home />} />
//                 <Route path="/chat" element={<Home />} />
//                 <Route path="*" element={<ErrorPage />} />
//                 <Route path="/upload" element={<FileUpload />} />
//             </Routes>
//         </BrowserRouter>
//     );
// }

// export default App;

import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import FileUpload from './pages/FileUpload';

function App(): React.ReactElement {
    return (
        <Router>
            <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/chat" element={<Home />} />
                <Route path="/upload" element={<FileUpload />} />
            </Routes>
        </Router>
    );
}

export default App;