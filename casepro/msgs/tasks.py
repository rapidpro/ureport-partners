from __future__ import absolute_import, unicode_literals

import six

from collections import defaultdict
from celery import shared_task
from celery.utils.log import get_task_logger
from dash.orgs.tasks import org_task
from datetime import timedelta

logger = get_task_logger(__name__)


@org_task('message-pull')
def pull_messages(org, since, until):
    """
    Pulls new unsolicited messages for an org
    """
    from casepro.backend import get_backend
    backend = get_backend()

    # if we're running for the first time, then we'll fetch back to 1 hour ago
    if not since:
        since = until - timedelta(hours=1)

    # TODO sync labels

    msgs_created, msgs_updated, msgs_deleted = backend.pull_messages(org, since, until)

    return {'messages': {'created': msgs_created, 'updated': msgs_updated, 'deleted': msgs_deleted}}


@org_task('message-handle')
def handle_messages(org, since, until):
    from casepro.backend import get_backend
    from casepro.cases.models import Case, Label
    from .models import Message
    backend = get_backend()

    # fetch all unhandled messages who now have full contacts
    unhandled = list(Message.objects.filter(org=org, is_handled=False, contact__is_stub=False).select_related('contact'))
    if not unhandled:
        return {'messages': 0, 'labelled': 0}

    labels_by_keyword = Label.get_keyword_map(org)
    label_matches = defaultdict(list)  # messages that match each label

    case_replies, labelled, unlabelled = [], [], []

    for msg in unhandled:
        open_case = Case.get_open_for_contact_on(org, msg.contact, msg.created_on)

        if open_case:
            open_case.reply_event(msg)

            case_replies.append(msg)
        else:
            # only apply labels if there isn't a currently open case for this contact
            matched_labels = msg.auto_label(labels_by_keyword)
            if matched_labels:
                labelled.append(msg)
                for label in matched_labels:
                    label_matches[label].append(msg)
            else:
                unlabelled.append(msg)

    # add labels to matching messages
    for label, matched_msgs in six.iteritems(label_matches):
        if matched_msgs:
            # TODO label locally
            backend.label_messages(org, matched_msgs, label)

    # archive messages which are case replies
    if case_replies:
        Message.objects.filter(pk__in=[m.pk for m in case_replies]).update(is_archived=True)
        backend.archive_messages(org, case_replies)

    # record the last labelled/unlabelled message times for this org
    if labelled:
        org.record_message_time(labelled[0].created_on, labelled=True)
    if unlabelled:
        org.record_message_time(unlabelled[0].created_on, labelled=False)

    # mark all of these messages as handled
    Message.objects.filter(pk__in=[m.pk for m in unhandled]).update(is_handled=True)

    return {'messages': len(unhandled), 'labelled': len(labelled)}


@shared_task
def message_export(export_id):
    from .models import MessageExport

    logger.info("Starting message export #%d..." % export_id)

    export = MessageExport.objects.get(pk=export_id)
    export.do_export()


@shared_task
def delete_old_messages():
    """
    We don't keep incoming messages forever unless they're labelled or associated with a case
    """
    from .models import Message

    # TODO
