from celery import shared_task

from .models import Experiment
from .services import maybe_auto_promote


@shared_task(ignore_result=True)
def evaluate_experiments():
    for experiment in Experiment.all_objects.filter(status="running", auto_promote=True):
        maybe_auto_promote(experiment)
