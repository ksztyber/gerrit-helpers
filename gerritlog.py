#!/usr/bin/env python3

import git
import itertools
import re


class Commit:
    _chgid_regex = re.compile(r'Change-Id:\s+([a-zA-Z0-9]+)')

    def __init__(self, commit: git.Commit):
        self._repo = commit.repo
        self._master = self._get_master()
        self.commit = commit
        self.change_id = self._get_change_id()
        self.is_merged = self._check_merged()
        self.title = self._get_title()
        self.sha = self._get_sha()
        self.shortsha = self._get_shortsha()

    def _get_change_id(self):
        for line in [ln.strip() for ln in self.commit.message.split('\n')]:
            if match := self._chgid_regex.match(line):
                return match.groups(1)[0]
        return None

    def _get_master(self):
        for head in self._repo.heads:
            if head.tracking_branch().name == 'origin/master':
                return head
        return None

    def _check_merged(self):
        head = self._master.tracking_branch().commit
        return (self.commit.hexsha in [c.hexsha for c in
                self._repo.merge_base(self.commit.hexsha, head.hexsha)])

    def _get_title(self):
        return self.commit.message.split('\n')[0]

    def _get_sha(self):
        return self.commit.hexsha

    def _get_shortsha(self):
        return self._repo.git.rev_parse(self._get_sha(), short=True)


def main():
    repo = git.repo.Repo()
    for c in repo.iter_commits():
        commit = Commit(c)
        print('{} {} {}'.format(commit.shortsha, commit.title,
                                '[merged]' if commit.is_merged else ''))


if __name__ == '__main__':
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
