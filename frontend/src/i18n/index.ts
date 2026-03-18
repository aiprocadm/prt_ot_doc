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
        settings: "Настройки",
        training: "Обучение",
        exports: "Выгрузки",
        marketplace: "Маркетплейс"
      },
      training: {
        title: "Обучение и инструктажи",
        teacherView: "Кабинет преподавателя",
        learnerView: "Кабинет слушателя",
        registry: "Реестр",
        completion: "Завершение"
      },
      exports: {
        title: "Экспорт и BI",
        jobs: "Задания",
        schedules: "Расписания",
        kpis: "KPI"
      }
    }
  },
  en: {
    translation: {
      auth: {
        login: "Sign in",
        email: "Email",
        password: "Password"
      },
      training: {
        title: "Training",
        teacherView: "Teacher cabinet",
        learnerView: "Learner cabinet",
        registry: "Registry",
        completion: "Completion"
      },
      exports: {
        title: "Exports and BI",
        jobs: "Jobs",
        schedules: "Schedules",
        kpis: "KPIs"
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
