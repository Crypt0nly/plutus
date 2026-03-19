import React, { useEffect } from "react";
import ReactDOM from "react-dom/client";
import {
  ClerkProvider,
  SignIn,
  SignedIn,
  SignedOut,
  useAuth,
} from "@clerk/clerk-react";
import App from "./App";
import "./index.css";
import { setTokenGetter } from "./lib/api";
import { setWsTokenGetter } from "./hooks/useWebSocket";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string;

/**
 * Injects the Clerk JWT token into the API client and WebSocket hook
 * so all requests are authenticated automatically.
 */
function ClerkTokenInjector() {
  const { getToken } = useAuth();

  useEffect(() => {
    const getter = () => getToken();
    setTokenGetter(getter);
    setWsTokenGetter(getter);
  }, [getToken]);

  return null;
}

/**
 * Full-screen sign-in page shown to unauthenticated users.
 */
function SignInPage() {
  return (
    <div className="h-screen flex items-center justify-center bg-gray-950">
      <SignIn
        appearance={{
          elements: {
            rootBox: "mx-auto",
            card: "bg-gray-900 border border-white/10 shadow-2xl",
            headerTitle: "text-white",
            headerSubtitle: "text-gray-400",
            socialButtonsBlockButton:
              "bg-gray-800 border border-white/10 text-white hover:bg-gray-700",
            formFieldLabel: "text-gray-300",
            formFieldInput:
              "bg-gray-800 border-white/10 text-white placeholder-gray-500",
            formButtonPrimary:
              "bg-plutus-600 hover:bg-plutus-700 text-white",
            footerActionLink: "text-plutus-400 hover:text-plutus-300",
            identityPreviewText: "text-gray-300",
            identityPreviewEditButton: "text-plutus-400",
          },
        }}
      />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
      <ClerkTokenInjector />
      <SignedOut>
        <SignInPage />
      </SignedOut>
      <SignedIn>
        <App />
      </SignedIn>
    </ClerkProvider>
  </React.StrictMode>
);
