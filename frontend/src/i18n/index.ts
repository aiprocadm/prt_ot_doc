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
        completion: "Завершение",
        groups: "Группы",
        enrollments: "Назначения",
        averageProgress: "Средний прогресс",
        assigned: "Назначено",
        completed: "Завершено",
        overdue: "Просрочено",
        nextDue: "Ближайший срок",
        materials: "Материалы",
        lessonStructure: "Структура курса",
        noSchedule: "Нет запланированной даты",
        learnerHint: "SCORM/xAPI/proctoring-ready ingestion отражается в статусах завершения и деталях назначения."
      },
      exports: {
        title: "Экспорт и BI",
        jobs: "Задания",
        schedules: "Расписания",
        kpis: "KPI",
        schemaVersion: "Версия схемы",
        anonymized: "Анонимизация",
        targetType: "Цель доставки"
      },
      common: {
        home: "Главная",
        loading: "Загрузка",
        locale: "Язык",
        localeRu: "Русский",
        localeEn: "English"
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
        completion: "Completion",
        groups: "Groups",
        enrollments: "Assignments",
        averageProgress: "Average progress",
        assigned: "Assigned",
        completed: "Completed",
        overdue: "Overdue",
        nextDue: "Next due",
        materials: "Materials",
        lessonStructure: "Course structure",
        noSchedule: "No schedule",
        learnerHint: "SCORM/xAPI/proctoring-ready ingestion is reflected in completion statuses and enrollment details."
      },
      exports: {
        title: "Exports and BI",
        jobs: "Jobs",
        schedules: "Schedules",
        kpis: "KPIs",
        schemaVersion: "Schema version",
        anonymized: "Anonymized",
        targetType: "Delivery target"
      },
      common: {
        home: "Home",
        loading: "Loading",
        locale: "Language",
        localeRu: "Russian",
        localeEn: "English"
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
