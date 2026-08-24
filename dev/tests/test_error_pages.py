from django.template.loader import render_to_string
from django.test import TestCase


class ErrorPageTests(TestCase):
    def test_404_page_uses_the_custom_template(self):
        response = self.client.get('/this-page-does-not-exist/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Page Not Found', status_code=404)
        self.assertContains(response, 'Back to Home', status_code=404)

    def test_500_template_renders_without_a_request_context(self):
        html = render_to_string('500.html')
        self.assertIn('Something Went Wrong', html)
