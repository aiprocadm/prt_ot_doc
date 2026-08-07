import { useState } from "react";
import { toast } from "sonner";

import { budgetApi } from "@/api/budget";
import { EmptyState } from "@/components/common/EmptyState";
import { Can } from "@/components/permissions/Can";
import { Button } from "@/components/ui/button";
import { ArticleFormDialog } from "@/features/budget/ArticleFormDialog";
import { BUDGET_DOMAIN_LABELS } from "@/pages/budget/budgetVocab";
import { PERMISSIONS } from "@/permissions/permissions";
import type {
  BudgetArticleDto,
  BudgetArticlePageDto,
} from "@/types/dto/budget";

interface Props {
  articles: BudgetArticlePageDto;
  onChanged: () => void;
}

export const ArticlesTab = ({ articles, onChanged }: Props) => {
  const [seeding, setSeeding] = useState(false);

  const seedDefaults = async () => {
    setSeeding(true);
    try {
      const result = await budgetApi.seedDefaultArticles();
      toast.success(
        `Добавлено: ${result.created}, пропущено: ${result.skipped}`,
      );
      onChanged();
    } catch (err) {
      toast.error(
        (err as { message?: string })?.message ??
          "Не удалось заполнить статьи по умолчанию",
      );
    } finally {
      setSeeding(false);
    }
  };

  const removeArticle = async (article: BudgetArticleDto) => {
    if (!window.confirm(`Удалить статью «${article.name}»?`)) return;
    try {
      await budgetApi.deleteArticle(article.id);
      onChanged();
    } catch {
      // Ошибку уже показал глобальный обработчик API.
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Can permission={PERMISSIONS.BUDGET_MANAGE}>
          <Button
            variant="outline"
            onClick={() => void seedDefaults()}
            disabled={seeding}
          >
            {seeding ? "Заполняем..." : "Заполнить стандартными"}
          </Button>
          <ArticleFormDialog
            trigger={<Button>Новая статья</Button>}
            onSubmitted={onChanged}
          />
        </Can>
      </div>

      {articles.items.length === 0 ? (
        <EmptyState
          title="Статей нет"
          description="Создайте статью или заполните стандартный набор."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4">Код</th>
                <th className="py-2 pr-4">Название</th>
                <th className="py-2 pr-4">Домен</th>
                <th className="py-2 pr-4">Статус</th>
                <th className="py-2">Действия</th>
              </tr>
            </thead>
            <tbody>
              {articles.items.map((article) => (
                <tr key={article.id} className="border-b last:border-0">
                  <td className="py-2 pr-4">{article.code}</td>
                  <td className="py-2 pr-4">{article.name}</td>
                  <td className="py-2 pr-4">
                    {article.domain
                      ? BUDGET_DOMAIN_LABELS[article.domain]
                      : "Универсальная"}
                  </td>
                  <td className="py-2 pr-4">
                    {article.is_active ? "Активна" : "Отключена"}
                  </td>
                  <td className="py-2">
                    <Can permission={PERMISSIONS.BUDGET_MANAGE}>
                      <div className="flex flex-wrap gap-1">
                        <ArticleFormDialog
                          trigger={
                            <Button size="sm" variant="outline">
                              Изменить
                            </Button>
                          }
                          initialData={article}
                          onSubmitted={onChanged}
                        />
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => void removeArticle(article)}
                        >
                          Удалить
                        </Button>
                      </div>
                    </Can>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
