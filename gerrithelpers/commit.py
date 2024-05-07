# This class mimics python-gerrit-api's
# gerrit.changes.comments.GerritChangeRevisionComment, as this is what
# gerritlog.py currently uses.  TODO: rework that.
class GerritCommit:
    def __init__(self, data):
        self.id = data['id']
        self.labels = {'Verified': {}, 'Code-Review': {'all': []}}
        self.status = data.get('status', 'UNKNOWN')
        self._parse_labels(data)

    def _parse_labels(self, data):
        patchset = data.get('currentPatchSet')
        if patchset is None:
            raise ValueError('Missing field: currentPatchSet')
        labels = patchset.get('approvals', [])
        verified = [l for l in labels if l['type'] == 'Verified']
        if len(verified) > 0:
            verified = verified[0]
            self.labels['Verified'] = {
                'approved': verified['value'] in ['1', '2'] or None,
                'rejected': verified['value'] not in ['1', '2'] or None}
        labels = patchset.get('approvals', [])
        for cr in [l for l in labels if l['type'] == 'Code-Review']:
            # Fix up the type of code review value
            cr['value'] = int(cr['value'])
            self.labels['Code-Review']['all'].append(cr)
