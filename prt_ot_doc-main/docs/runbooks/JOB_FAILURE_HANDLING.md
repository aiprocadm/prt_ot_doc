# JOB_FAILURE_HANDLING

Симптомы: рост failed jobs.
Проверки: worker logs, queue depth, retries.
Действия: retry для transient, rollback/escalate для data corruption.
