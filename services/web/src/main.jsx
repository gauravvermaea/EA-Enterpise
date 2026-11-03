import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { initAuth } from "./auth";
import "./styles.css";

initAuth().then(() => {
  createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
});
