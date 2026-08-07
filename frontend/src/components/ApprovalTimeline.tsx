type TimelineItem = {
  decision: string;
  comment?: string | null;
  step_no: number;
};

type Props = {
  items: TimelineItem[];
  currentStep: number;
};

const ApprovalTimeline = ({ items, currentStep }: Props) => (
  <div className="rounded-lg border p-4 space-y-2">
    <div className="text-sm font-medium">
      Timeline (current step: {currentStep})
    </div>
    {items.length === 0 ? (
      <div className="text-sm text-muted-foreground">Решений пока нет</div>
    ) : (
      items.map((it, idx) => (
        <div key={`${idx}-${it.step_no}`} className="text-sm">
          Step {it.step_no}: <b>{it.decision}</b>{" "}
          {it.comment ? `— ${it.comment}` : ""}
        </div>
      ))
    )}
  </div>
);

export default ApprovalTimeline;
