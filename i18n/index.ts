import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  ru: {
    translation: {
      auth: {
        login: "Войти",
        email: "E-mail",
        password: "Пароль"
      },
      navigation: {
        companies: "Компании",
        persons: "Сотрудники",
        templates: "Шаблоны",
        packs: "Пакеты",
        documents: "Документы",
        files: "Файлы",
        tasks: "Задачи",
        risk: "Риски",
        npa: "НПА",
        audit: "Аудит",
        settings: "Настройки"
      }
    }
  },
  en: {
    translation: {
      auth: {
        login: "Sign in",
        email: "Email",
        password: "Password"
      }
    }
  }
};

i18n.use(initReactI18next).init({
  resources,
  lng: "ru",
  fallbackLng: "ru",
  interpolation: {
    escapeValue: false
  }
});

export default i18n;
