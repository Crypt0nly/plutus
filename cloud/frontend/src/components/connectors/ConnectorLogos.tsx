/**
 * Official brand SVG logos for all Plutus connectors.
 *
 * Each component accepts a `className` and `size` prop (default 24).
 * Logos are inline SVGs — no external dependencies, pixel-perfect at any size.
 */

interface LogoProps {
  className?: string;
  size?: number;
}

/* ── Messaging ─────────────────────────────────────────────────────────── */

export function TelegramLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 240 240" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="tg-grad" x1="120" y1="0" x2="120" y2="240" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#2AABEE" />
          <stop offset="100%" stopColor="#229ED9" />
        </linearGradient>
      </defs>
      <circle cx="120" cy="120" r="120" fill="url(#tg-grad)" />
      <path
        d="M54 117.3l109.5-42.2c5.1-1.8 9.5 1.2 7.8 8.8l-18.7 88.1c-1.4 6.1-5 7.6-10.2 4.7l-28-20.6-13.5 13c-1.5 1.5-2.8 2.7-5.7 2.7l2-28.8 52.2-47.2c2.3-2-0.5-3.1-3.5-1.1L75.4 140.5 48 132.1c-6-1.9-6.1-6 1-8.8z"
        fill="white"
      />
    </svg>
  );
}

export function WhatsAppLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 175.216 175.552" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="wa-grad" x1="85.915" y1="132.913" x2="86.535" y2="52.569" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#20B038" />
          <stop offset="100%" stopColor="#60D66A" />
        </linearGradient>
      </defs>
      <path
        d="M87.184 25.227c-33.733 0-61.166 27.423-61.178 61.13a60.98 60.98 0 0 0 8.177 30.544L26 149.138l33.913-8.884a61.25 61.25 0 0 0 29.282 7.456h.025c33.72 0 61.144-27.423 61.156-61.13.013-16.32-6.332-31.67-17.845-43.212-11.51-11.544-26.82-17.9-43.147-17.9zm0 112.332a50.95 50.95 0 0 1-25.994-7.116l-1.86-1.105-19.328 5.07 5.155-18.835-1.21-1.924a50.78 50.78 0 0 1-7.808-27.018c.012-28.11 22.887-50.975 51.01-50.975 13.617.005 26.414 5.316 36.05 14.963 9.638 9.645 14.945 22.444 14.94 36.08-.015 28.112-22.89 50.86-51 50.86zm27.98-38.147c-1.533-.767-9.074-4.478-10.48-4.988-1.407-.51-2.43-.767-3.453.768-1.022 1.534-3.963 4.988-4.858 6.012-.896 1.022-1.79 1.15-3.324.383-1.533-.768-6.476-2.387-12.33-7.61-4.558-4.066-7.635-9.08-8.53-10.614-.895-1.534-.095-2.365.673-3.13.69-.688 1.534-1.79 2.3-2.686.768-.895 1.022-1.534 1.534-2.556.51-1.022.255-1.918-.128-2.686-.383-.767-3.453-8.32-4.73-11.39-1.244-2.99-2.51-2.586-3.453-2.634-.895-.044-1.918-.053-2.94-.053a5.65 5.65 0 0 0-4.093 1.918c-1.407 1.534-5.37 5.245-5.37 12.798 0 7.553 5.497 14.85 6.264 15.872.768 1.022 10.818 16.52 26.215 23.17 3.664 1.582 6.52 2.527 8.748 3.234 3.677 1.17 7.02 1.004 9.668.61 2.95-.44 9.074-3.71 10.354-7.293 1.278-3.582 1.278-6.65.895-7.293-.383-.64-1.407-1.022-2.94-1.79z"
        fill="url(#wa-grad)"
      />
    </svg>
  );
}

export function DiscordLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 -28.5 256 256" className={className} xmlns="http://www.w3.org/2000/svg">
      <path
        d="M216.856 16.597A208.502 208.502 0 0 0 164.042 0c-2.275 4.113-4.933 9.645-6.766 14.046-19.692-2.961-39.203-2.961-58.533 0-1.832-4.4-4.55-9.933-6.846-14.046a207.809 207.809 0 0 0-52.855 16.638C5.618 67.147-3.443 116.4 1.087 164.956c22.169 16.555 43.653 26.612 64.775 33.193A161.094 161.094 0 0 0 79.735 175.3a136.413 136.413 0 0 1-21.846-10.632 108.636 108.636 0 0 0 5.356-4.237c42.122 19.702 87.89 19.702 129.51 0a131.66 131.66 0 0 0 5.355 4.237 136.07 136.07 0 0 1-21.886 10.653c4.006 8.02 8.638 15.67 13.873 22.848 21.142-6.58 42.646-16.637 64.815-33.213 5.316-56.288-9.08-105.09-38.056-148.36zM85.474 135.095c-12.645 0-23.015-11.805-23.015-26.18s10.149-26.2 23.015-26.2c12.867 0 23.236 11.804 23.015 26.2.02 14.375-10.148 26.18-23.015 26.18zm85.051 0c-12.645 0-23.014-11.805-23.014-26.18s10.148-26.2 23.014-26.2c12.867 0 23.236 11.804 23.015 26.2 0 14.375-10.148 26.18-23.015 26.18z"
        fill="#5865F2"
      />
    </svg>
  );
}

/* ── AI Providers ──────────────────────────────────────────────────────── */

export function OpenAILogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <path
        d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.896zm16.597 3.855l-5.843-3.372L15.115 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.403-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"
        fill="currentColor"
      />
    </svg>
  );
}

export function AnthropicLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <path
        d="M13.827 3.52h3.603L24 20h-3.603l-6.57-16.48zm-7.258 0h3.767L16.906 20h-3.674l-1.343-3.461H5.017L3.674 20H0L6.569 3.52zm4.132 9.959L8.453 7.687 6.205 13.479h4.496z"
        fill="currentColor"
      />
    </svg>
  );
}

export function GeminiLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" className={className} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="gem-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#4285F4" />
          <stop offset="50%" stopColor="#9B72CB" />
          <stop offset="100%" stopColor="#D96570" />
        </linearGradient>
      </defs>
      <path
        d="M14 28C14 26.0633 13.6267 24.2433 12.88 22.54C12.1567 20.8367 11.165 19.355 9.905 18.095C8.645 16.835 7.16333 15.8433 5.46 15.12C3.75667 14.3733 1.93667 14 0 14C1.93667 14 3.75667 13.6383 5.46 12.915C7.16333 12.1683 8.645 11.165 9.905 9.905C11.165 8.645 12.1567 7.16333 12.88 5.46C13.6267 3.75667 14 1.93667 14 0C14 1.93667 14.3617 3.75667 15.085 5.46C15.8317 7.16333 16.835 8.645 18.095 9.905C19.355 11.165 20.8367 12.1683 22.54 12.915C24.2433 13.6383 26.0633 14 28 14C26.0633 14 24.2433 14.3733 22.54 15.12C20.8367 15.8433 19.355 16.835 18.095 18.095C16.835 19.355 15.8317 20.8367 15.085 22.54C14.3617 24.2433 14 26.0633 14 28Z"
        fill="url(#gem-grad)"
      />
    </svg>
  );
}

export function OllamaLogo({ className, size = 24 }: LogoProps) {
  // Ollama's official mark — a stylised llama head
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="50" fill="#1a1a1a" />
      {/* Ears */}
      <ellipse cx="32" cy="24" rx="8" ry="12" fill="white" transform="rotate(-15 32 24)" />
      <ellipse cx="68" cy="24" rx="8" ry="12" fill="white" transform="rotate(15 68 24)" />
      {/* Head */}
      <ellipse cx="50" cy="52" rx="26" ry="28" fill="white" />
      {/* Eyes */}
      <circle cx="40" cy="46" r="5" fill="#1a1a1a" />
      <circle cx="60" cy="46" r="5" fill="#1a1a1a" />
      <circle cx="41.5" cy="44.5" r="1.5" fill="white" />
      <circle cx="61.5" cy="44.5" r="1.5" fill="white" />
      {/* Nose */}
      <ellipse cx="50" cy="57" rx="5" ry="3.5" fill="#e0a0a0" />
      {/* Mouth */}
      <path d="M45 62 Q50 66 55 62" stroke="#999" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/* ── Developer ─────────────────────────────────────────────────────────── */

export function GitHubLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <path
        d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
        fill="currentColor"
      />
    </svg>
  );
}

/* ── Google ─────────────────────────────────────────────────────────────── */

export function GmailLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M24 5.457v13.909c0 .904-.732 1.636-1.636 1.636h-3.819V11.73L12 16.64l-6.545-4.91v9.273H1.636A1.636 1.636 0 0 1 0 19.366V5.457c0-2.023 2.309-3.178 3.927-1.964L5.455 4.64 12 9.548l6.545-4.91 1.528-1.145C21.69 2.28 24 3.434 24 5.457z" fill="#EA4335" />
      <path d="M0 5.457v13.909c0 .904.732 1.636 1.636 1.636h3.819V11.73L12 16.64V9.548L5.455 4.64 3.927 3.493C2.309 2.28 0 3.434 0 5.457z" fill="#34A853" />
      <path d="M18.545 11.73v9.273h3.819A1.636 1.636 0 0 0 24 19.366V5.457c0-2.023-2.309-3.178-3.927-1.964L18.545 4.64v7.09z" fill="#4285F4" />
      <path d="M12 9.548l6.545-4.91-1.528-1.145C15.4 2.28 12 3.434 12 5.457v4.09z" fill="#FBBC05" />
    </svg>
  );
}

export function GoogleCalendarLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M18.316 5.684H24v12.632h-5.684z" fill="#EA4335" />
      <path d="M5.684 24h12.632v-5.684H5.684z" fill="#34A853" />
      <path d="M0 18.316h5.684V5.684H0z" fill="#4285F4" />
      <path d="M5.684 5.684h12.632V0H5.684z" fill="#FBBC05" />
      <path d="M5.684 18.316h12.632V5.684H5.684z" fill="white" />
      <path d="M18.316 18.316H24v5.684h-5.684z" fill="#188038" />
      <path d="M0 24h5.684v-5.684H0z" fill="#1967D2" />
      <path d="M0 5.684h5.684V0H0z" fill="#FBBC05" />
      <path d="M24 0h-5.684v5.684H24z" fill="#1967D2" />
      <text x="12" y="15.5" textAnchor="middle" fontSize="8" fontWeight="bold" fill="#1967D2" fontFamily="Arial">31</text>
    </svg>
  );
}

export function GoogleDriveLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 87.3 78" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H0c0 1.55.4 3.1 1.2 4.5z" fill="#0066DA" />
      <path d="M43.65 25L29.9 1.2C28.55 2 27.4 3.1 26.6 4.5L1.2 48.5C.4 49.9 0 51.45 0 53h27.5z" fill="#00AC47" />
      <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5H60l5.85 11.5z" fill="#EA4335" />
      <path d="M43.65 25L57.4 1.2C56.05.4 54.5 0 52.9 0H34.4c-1.6 0-3.15.45-4.5 1.2z" fill="#00832D" />
      <path d="M60 53H27.5L13.75 76.8c1.35.8 2.9 1.2 4.5 1.2h50.5c1.6 0 3.15-.45 4.5-1.2z" fill="#2684FC" />
      <path d="M73.4 26.5l-12.65-21.9C59.95 3.2 58.8 2.1 57.45 1.3L43.7 25 60.1 53h27.2c0-1.55-.4-3.1-1.2-4.5z" fill="#FFBA00" />
    </svg>
  );
}

/* ── Hosting ────────────────────────────────────────────────────────────── */

export function VercelLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 116 100" className={className} xmlns="http://www.w3.org/2000/svg">
      <path d="M57.5 0L115 100H0L57.5 0z" fill="currentColor" />
    </svg>
  );
}

export function NetlifyLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" className={className} xmlns="http://www.w3.org/2000/svg">
      <path
        d="M307.3 245.5l-53.8-53.8 53.8-53.8 53.8 53.8-53.8 53.8zM204.7 266.5l53.8 53.8-53.8 53.8-53.8-53.8 53.8-53.8zM256 0C114.6 0 0 114.6 0 256s114.6 256 256 256 256-114.6 256-256S397.4 0 256 0zm107.1 148.9l-53.8 53.8-53.8-53.8 53.8-53.8 53.8 53.8zm-214.2 0l53.8 53.8-53.8 53.8-53.8-53.8 53.8-53.8zm0 214.2l-53.8-53.8 53.8-53.8 53.8 53.8-53.8 53.8zm214.2 0l-53.8-53.8 53.8-53.8 53.8 53.8-53.8 53.8z"
        fill="#00AD9F"
      />
    </svg>
  );
}

/* ── Email (generic) ────────────────────────────────────────────────────── */

export function EmailLogo({ className, size = 24 }: LogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="4" width="20" height="16" rx="2" fill="#F59E0B" />
      <path d="M2 7l10 7 10-7" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" />
    </svg>
  );
}

/* ── Master map: connector name → logo component ─────────────────────── */

export const CONNECTOR_LOGO_MAP: Record<string, React.ComponentType<LogoProps>> = {
  telegram: TelegramLogo,
  whatsapp: WhatsAppLogo,
  discord: DiscordLogo,
  openai: OpenAILogo,
  anthropic: AnthropicLogo,
  gemini: GeminiLogo,
  google_gemini: GeminiLogo,
  ollama: OllamaLogo,
  github: GitHubLogo,
  google_gmail: GmailLogo,
  gmail: GmailLogo,
  email: EmailLogo,
  google_calendar: GoogleCalendarLogo,
  google_drive: GoogleDriveLogo,
  vercel: VercelLogo,
  netlify: NetlifyLogo,
};

/**
 * Convenience component: renders the correct brand logo for a connector name,
 * falling back to null if no logo is registered.
 */
export function ConnectorLogo({
  name,
  size = 24,
  className,
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const Logo = CONNECTOR_LOGO_MAP[name.toLowerCase()];
  if (!Logo) return null;
  return <Logo size={size} className={className} />;
}
