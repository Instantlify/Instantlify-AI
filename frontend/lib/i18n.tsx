"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

/**
 * Lightweight UI translations. Add a key to EN first (it is the fallback and the
 * source of truth), then to each language; a missing translation shows English.
 * Customer-facing pages (forms, link in bio, web chat) and the app navigation are
 * translated; other screens are English until their strings are moved here.
 * The non-English text was written without native review: have it checked.
 */
export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "de", label: "Deutsch" },
  { code: "fr", label: "Français" },
  { code: "ru", label: "Русский" },
  { code: "sr", label: "Srpski" },
] as const;
export type Language = (typeof LANGUAGES)[number]["code"];

const EN = {
  "nav.overview": "Home",
  "nav.inbox": "Conversations",
  "nav.crm": "Contacts",
  "nav.automations": "Automation",
  "nav.channels": "Channels",
  "nav.integrations": "Integrations",
  "nav.agent": "AI agent",
  "nav.analytics": "Analytics",
  "nav.templates": "Templates",
  "nav.payments": "Payments",
  "nav.team": "Team",
  "nav.activity": "Activity",
  "nav.help": "Help & support",
  "nav.settings": "Settings",
  "nav.language": "Language",
  "form.loading": "Loading form…",
  "form.unavailable": "This form is unavailable.",
  "form.submit": "Send response",
  "form.submitting": "Submitting…",
  "form.yes": "Yes",
  "form.no": "No",
  "form.choose": "Choose an option",
  "form.firstName": "First name",
  "form.lastName": "Last name",
  "form.email": "Email address",
  "form.phone": "Phone number",
  "form.signatureHelp":
    "Draw your signature in the box, or upload a signature image.",
  "bio.name": "Your name (optional)",
  "bio.email": "you@example.com",
  "bio.subscribed": "Thanks, you're on the list.",
  "bio.madeWith": "Made with",
  "auth.signIn": "Sign in",
  "auth.createAccount": "Create account",
  "auth.wait": "Please wait…",
  "auth.forgot": "Forgot your password?",
  "auth.magicLink": "Email me a sign-in link",
  "auth.google": "Continue with Google",
} as const;
export type MessageKey = keyof typeof EN;
type Dictionary = Partial<Record<MessageKey, string>>;

const ES: Dictionary = {
  "nav.overview": "Inicio",
  "nav.inbox": "Conversaciones",
  "nav.crm": "Contactos",
  "nav.automations": "Automatización",
  "nav.channels": "Canales",
  "nav.integrations": "Integraciones",
  "nav.agent": "Agente de IA",
  "nav.analytics": "Analítica",
  "nav.templates": "Plantillas",
  "nav.payments": "Pagos",
  "nav.team": "Equipo",
  "nav.activity": "Actividad",
  "nav.help": "Ayuda y soporte",
  "nav.settings": "Ajustes",
  "nav.language": "Idioma",
  "form.loading": "Cargando formulario…",
  "form.unavailable": "Este formulario no está disponible.",
  "form.submit": "Enviar respuesta",
  "form.submitting": "Enviando…",
  "form.yes": "Sí",
  "form.no": "No",
  "form.choose": "Elige una opción",
  "form.firstName": "Nombre",
  "form.lastName": "Apellido",
  "form.email": "Correo electrónico",
  "form.phone": "Teléfono",
  "form.signatureHelp":
    "Dibuja tu firma en el recuadro o sube una imagen de tu firma.",
  "bio.name": "Tu nombre (opcional)",
  "bio.email": "tu@ejemplo.com",
  "bio.subscribed": "¡Gracias, ya estás en la lista!",
  "bio.madeWith": "Hecho con",
  "auth.signIn": "Iniciar sesión",
  "auth.createAccount": "Crear cuenta",
  "auth.wait": "Espera un momento…",
  "auth.forgot": "¿Olvidaste tu contraseña?",
  "auth.magicLink": "Envíame un enlace de acceso",
  "auth.google": "Continuar con Google",
};

const DE: Dictionary = {
  "nav.overview": "Start",
  "nav.inbox": "Unterhaltungen",
  "nav.crm": "Kontakte",
  "nav.automations": "Automatisierung",
  "nav.channels": "Kanäle",
  "nav.integrations": "Integrationen",
  "nav.agent": "KI-Agent",
  "nav.analytics": "Analysen",
  "nav.templates": "Vorlagen",
  "nav.payments": "Zahlungen",
  "nav.team": "Team",
  "nav.activity": "Aktivität",
  "nav.help": "Hilfe & Support",
  "nav.settings": "Einstellungen",
  "nav.language": "Sprache",
  "form.loading": "Formular wird geladen…",
  "form.unavailable": "Dieses Formular ist nicht verfügbar.",
  "form.submit": "Antwort senden",
  "form.submitting": "Wird gesendet…",
  "form.yes": "Ja",
  "form.no": "Nein",
  "form.choose": "Option wählen",
  "form.firstName": "Vorname",
  "form.lastName": "Nachname",
  "form.email": "E-Mail-Adresse",
  "form.phone": "Telefonnummer",
  "form.signatureHelp":
    "Zeichne deine Unterschrift in das Feld oder lade ein Bild hoch.",
  "bio.name": "Dein Name (optional)",
  "bio.email": "du@beispiel.de",
  "bio.subscribed": "Danke, du bist auf der Liste.",
  "bio.madeWith": "Erstellt mit",
  "auth.signIn": "Anmelden",
  "auth.createAccount": "Konto erstellen",
  "auth.wait": "Bitte warten…",
  "auth.forgot": "Passwort vergessen?",
  "auth.magicLink": "Anmeldelink per E-Mail senden",
  "auth.google": "Weiter mit Google",
};

const FR: Dictionary = {
  "nav.overview": "Accueil",
  "nav.inbox": "Conversations",
  "nav.crm": "Contacts",
  "nav.automations": "Automatisation",
  "nav.channels": "Canaux",
  "nav.integrations": "Intégrations",
  "nav.agent": "Agent IA",
  "nav.analytics": "Statistiques",
  "nav.templates": "Modèles",
  "nav.payments": "Paiements",
  "nav.team": "Équipe",
  "nav.activity": "Activité",
  "nav.help": "Aide et support",
  "nav.settings": "Paramètres",
  "nav.language": "Langue",
  "form.loading": "Chargement du formulaire…",
  "form.unavailable": "Ce formulaire n'est pas disponible.",
  "form.submit": "Envoyer la réponse",
  "form.submitting": "Envoi…",
  "form.yes": "Oui",
  "form.no": "Non",
  "form.choose": "Choisissez une option",
  "form.firstName": "Prénom",
  "form.lastName": "Nom",
  "form.email": "Adresse e-mail",
  "form.phone": "Numéro de téléphone",
  "form.signatureHelp":
    "Dessinez votre signature dans le cadre ou importez une image.",
  "bio.name": "Votre nom (facultatif)",
  "bio.email": "vous@exemple.fr",
  "bio.subscribed": "Merci, vous êtes inscrit.",
  "bio.madeWith": "Créé avec",
  "auth.signIn": "Se connecter",
  "auth.createAccount": "Créer un compte",
  "auth.wait": "Veuillez patienter…",
  "auth.forgot": "Mot de passe oublié ?",
  "auth.magicLink": "Recevoir un lien de connexion",
  "auth.google": "Continuer avec Google",
};

const RU: Dictionary = {
  "nav.overview": "Главная",
  "nav.inbox": "Диалоги",
  "nav.crm": "Контакты",
  "nav.automations": "Автоматизация",
  "nav.channels": "Каналы",
  "nav.integrations": "Интеграции",
  "nav.agent": "ИИ-агент",
  "nav.analytics": "Аналитика",
  "nav.templates": "Шаблоны",
  "nav.payments": "Платежи",
  "nav.team": "Команда",
  "nav.activity": "Активность",
  "nav.help": "Помощь и поддержка",
  "nav.settings": "Настройки",
  "nav.language": "Язык",
  "form.loading": "Загрузка формы…",
  "form.unavailable": "Эта форма недоступна.",
  "form.submit": "Отправить ответ",
  "form.submitting": "Отправка…",
  "form.yes": "Да",
  "form.no": "Нет",
  "form.choose": "Выберите вариант",
  "form.firstName": "Имя",
  "form.lastName": "Фамилия",
  "form.email": "Электронная почта",
  "form.phone": "Номер телефона",
  "form.signatureHelp":
    "Нарисуйте подпись в поле или загрузите изображение подписи.",
  "bio.name": "Ваше имя (необязательно)",
  "bio.email": "vy@primer.ru",
  "bio.subscribed": "Спасибо, вы в списке.",
  "bio.madeWith": "Сделано в",
  "auth.signIn": "Войти",
  "auth.createAccount": "Создать аккаунт",
  "auth.wait": "Подождите…",
  "auth.forgot": "Забыли пароль?",
  "auth.magicLink": "Прислать ссылку для входа",
  "auth.google": "Продолжить с Google",
};

const SR: Dictionary = {
  "nav.overview": "Početna",
  "nav.inbox": "Razgovori",
  "nav.crm": "Kontakti",
  "nav.automations": "Automatizacija",
  "nav.channels": "Kanali",
  "nav.integrations": "Integracije",
  "nav.agent": "AI agent",
  "nav.analytics": "Analitika",
  "nav.templates": "Šabloni",
  "nav.payments": "Plaćanja",
  "nav.team": "Tim",
  "nav.activity": "Aktivnost",
  "nav.help": "Pomoć i podrška",
  "nav.settings": "Podešavanja",
  "nav.language": "Jezik",
  "form.loading": "Učitavanje obrasca…",
  "form.unavailable": "Ovaj obrazac nije dostupan.",
  "form.submit": "Pošalji odgovor",
  "form.submitting": "Slanje…",
  "form.yes": "Da",
  "form.no": "Ne",
  "form.choose": "Izaberite opciju",
  "form.firstName": "Ime",
  "form.lastName": "Prezime",
  "form.email": "Imejl adresa",
  "form.phone": "Broj telefona",
  "form.signatureHelp": "Nacrtajte potpis u polju ili otpremite sliku potpisa.",
  "bio.name": "Vaše ime (opciono)",
  "bio.email": "vi@primer.rs",
  "bio.subscribed": "Hvala, na listi ste.",
  "bio.madeWith": "Napravljeno uz",
  "auth.signIn": "Prijava",
  "auth.createAccount": "Napravi nalog",
  "auth.wait": "Sačekajte…",
  "auth.forgot": "Zaboravili ste lozinku?",
  "auth.magicLink": "Pošalji mi link za prijavu",
  "auth.google": "Nastavi uz Google",
};

const DICTIONARIES: Record<Language, Dictionary> = {
  en: EN,
  es: ES,
  de: DE,
  fr: FR,
  ru: RU,
  sr: SR,
};
const STORAGE_KEY = "nemio:language";

export function detectLanguage(): Language {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && saved in DICTIONARIES) return saved as Language;
  } catch {
    // Storage unavailable: fall back to the browser language.
  }
  const browser = (typeof navigator !== "undefined" ? navigator.language : "en")
    .slice(0, 2)
    .toLowerCase();
  return (browser in DICTIONARIES ? browser : "en") as Language;
}

export function translate(language: Language, key: MessageKey) {
  return DICTIONARIES[language]?.[key] ?? EN[key];
}

const LanguageContext = createContext<{
  language: Language;
  setLanguage: (language: Language) => void;
}>({ language: "en", setLanguage: () => undefined });

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setState] = useState<Language>("en");
  useEffect(() => {
    queueMicrotask(() => setState(detectLanguage()));
  }, []);
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);
  const setLanguage = useCallback((next: Language) => {
    setState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not persisted; applies for this visit.
    }
  }, []);
  return (
    <LanguageContext.Provider value={{ language, setLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage() {
  return useContext(LanguageContext);
}

/** `const t = useT(); t("nav.inbox")` */
export function useT() {
  const { language } = useContext(LanguageContext);
  return useCallback((key: MessageKey) => translate(language, key), [language]);
}

export function LanguageSwitcher({ className }: { className?: string }) {
  const { language, setLanguage } = useLanguage();
  const t = useT();
  return (
    <select
      aria-label={t("nav.language")}
      className={className}
      value={language}
      onChange={(event) => setLanguage(event.target.value as Language)}
    >
      {LANGUAGES.map((item) => (
        <option key={item.code} value={item.code}>
          {item.label}
        </option>
      ))}
    </select>
  );
}
