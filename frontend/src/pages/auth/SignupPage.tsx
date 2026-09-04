import { useState } from "react";
import { Link } from "react-router-dom";

import { signup, type SignupResult } from "@/api/signup";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApiError } from "@/types/dto/common";

/**
 * Самостоятельная регистрация (BIZ-53 срез-3, Доп. №1 разд. 53.2).
 *
 * ТЗ обещает старт «без долгой настройки», поэтому полей ровно столько, сколько
 * нужно, чтобы войти: каждое лишнее здесь — причина не дойти до конца.
 *
 * **Закрытая регистрация объясняется словами.** Ручка выключена по умолчанию и
 * отвечает 404. Показать на это общую ошибку значило бы оставить человека
 * гадать, сломалось оно или так задумано.
 */

const asApiError = (err: unknown, fallback: string): ApiError =>
  err && typeof err === "object" && "message" in err
    ? (err as ApiError)
    : { status: 0, message: fallback };

const SignupPage = () => {
  const [slug, setSlug] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<SignupResult | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setClosed(false);
    try {
      setDone(
        await signup({
          slug: slug.trim().toLowerCase(),
          company_name: companyName.trim(),
          owner_email: email.trim(),
          owner_password: password,
        }),
      );
    } catch (err) {
      const apiError = asApiError(err, "Не удалось зарегистрироваться");
      if (apiError.status === 404) setClosed(true);
      else if (apiError.status === 409)
        setError("Такой адрес уже занят — придумайте другой.");
      else if (apiError.status === 429)
        setError("Слишком много попыток с этого адреса. Попробуйте позже.");
      else setError(apiError.message ?? "Не удалось зарегистрироваться");
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <div className="space-y-3" data-testid="signup-done">
        <h1 className="text-xl font-semibold">Готово</h1>
        <p className="text-sm text-muted-foreground">
          Рабочее пространство <strong>{done.tenant_slug}</strong> создано.
          Входите под <strong>{done.owner_email}</strong> с паролем, который вы
          только что задали.
        </p>
        {done.warnings.length > 0 ? (
          // Предупреждения выдачи не прячем: иначе человек увидит пустые
          // справочники и не поймёт, почему.
          <ul className="space-y-1 text-xs text-muted-foreground">
            {done.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
        <Button asChild>
          <Link to="/auth/login">Перейти ко входу</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Создать рабочее пространство</h1>

      {closed ? (
        <p
          className="text-sm text-muted-foreground"
          data-testid="signup-closed"
        >
          Самостоятельная регистрация на этой платформе закрыта. Обратитесь к
          владельцу платформы — он заведёт рабочее пространство за вас.
        </p>
      ) : (
        <>
          <div className="space-y-1.5">
            <Label htmlFor="signup-company">Название организации</Label>
            <Input
              id="signup-company"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="ООО «Ромашка»"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signup-slug">Адрес рабочего пространства</Label>
            <Input
              id="signup-slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="romashka"
            />
            <p className="text-xs text-muted-foreground">
              Строчные латинские буквы, цифры и дефис.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signup-email">Электронная почта владельца</Label>
            <Input
              id="signup-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="owner@romashka.ru"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="signup-password">Пароль</Label>
            <Input
              id="signup-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Не короче восьми символов"
            />
          </div>

          {error ? (
            <p className="text-sm text-destructive" data-testid="signup-error">
              {error}
            </p>
          ) : null}

          <Button onClick={() => void submit()} disabled={busy}>
            {busy ? "Создаём…" : "Создать"}
          </Button>
        </>
      )}

      <p className="text-sm text-muted-foreground">
        Уже есть пространство?{" "}
        <Link to="/auth/login" className="underline underline-offset-4">
          Войти
        </Link>
      </p>
    </div>
  );
};

export default SignupPage;
