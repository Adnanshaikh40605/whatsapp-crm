from celery import shared_task
from django.utils import timezone


@shared_task
def start_followup_sequence(sequence_id: str, lead_id: str):
    from apps.automation.models import FollowUpExecution, FollowUpSequence
    from apps.crm.models import Lead

    sequence = FollowUpSequence.objects.filter(id=sequence_id, is_active=True).first()
    lead = Lead.objects.filter(id=lead_id).first()
    if not sequence or not lead:
        return {"status": "not_found"}

    steps = sequence.steps or []
    delay_days = steps[0].get("delay_days", 0) if steps else 0
    next_run = timezone.now() + timezone.timedelta(days=delay_days)

    execution, created = FollowUpExecution.objects.get_or_create(
        organization=lead.organization,
        sequence=sequence,
        lead=lead,
        defaults={"next_run_at": next_run, "status": FollowUpExecution.Status.ACTIVE},
    )
    return {"status": "started", "execution_id": str(execution.id), "created": created}


@shared_task
def process_followup_sequences():
    from apps.automation.engine import FollowUpRunner
    FollowUpRunner.process_due_executions()
    return {"status": "processed"}


@shared_task
def dispatch_workflow(organization_id: str, trigger: str, context: dict):
    from apps.automation.engine import WorkflowEngine
    from apps.organizations.models import Organization

    org = Organization.objects.filter(id=organization_id).first()
    if org:
        WorkflowEngine.dispatch(org, trigger, context)
    return {"status": "dispatched"}
