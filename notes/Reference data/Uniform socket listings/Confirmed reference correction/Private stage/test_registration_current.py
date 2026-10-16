"""Repeat the negative checks after registration, with an idempotent baseline."""
import json
import unittest
import test_registration_preflight as prior

class CurrentRegistrationTests(prior.PreflightTests):
    def test_other_seventy_items_preserved(self):
        original=json.loads(self.adapter_before.decode('utf-8-sig'))
        target=prior.app.target_of(self.item)
        old=[x for x in original['pages'] if prior.app.target_of(x)!=target]
        new=[x for x in self.adapter['pages'] if prior.app.target_of(x)!=target]
        self.assertEqual(len(old),70);self.assertEqual(old,new)
        self.assertEqual(self.item['page'],'A1232-01')

if __name__=='__main__':unittest.main()
