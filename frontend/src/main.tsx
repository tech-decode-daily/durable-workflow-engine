import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import "@fontsource-variable/inter";
import "@fontsource/ibm-plex-mono/400.css";
import "./style.css";
import App from "./App";

const client = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 1000 } },
});
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
      <Toaster theme="dark" richColors position="bottom-right" />
    </QueryClientProvider>
  </React.StrictMode>,
);
