import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./styles.css";
import "./styles-multiline-base.css";
import "./styles-multiline-table.css";
import "./styles-multiline-responsive.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>
);
