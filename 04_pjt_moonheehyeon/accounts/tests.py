from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AccountTests(TestCase):
    def setUp(self):
        self.password = 'Reader-test-pass-42'
        self.user = get_user_model().objects.create_user(username='reader', password=self.password)

    def test_signup_uses_custom_user_and_logs_in(self):
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'newreader', 'password1': self.password, 'password2': self.password,
        })
        self.assertRedirects(response, reverse('books:index'))
        user = get_user_model().objects.get(username='newreader')
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.assertTrue(user.check_password(self.password))

    def test_invalid_login_and_signup_show_errors(self):
        response = self.client.post(reverse('accounts:login'), {'username': 'reader', 'password': 'wrong'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'reader', 'password1': self.password, 'password2': 'different',
        })
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_login_and_logout(self):
        response = self.client.post(reverse('accounts:login'), {'username': 'reader', 'password': self.password})
        self.assertRedirects(response, reverse('books:index'))
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(reverse('accounts:logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('accounts:logout')), reverse('books:index'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_update_cannot_change_privileges(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:update'), {
            'email': 'reader@example.com', 'first_name': '이름', 'last_name': '성',
            'is_staff': 'on', 'is_superuser': 'on',
        })
        self.assertRedirects(response, reverse('books:index'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'reader@example.com')
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_password_change_keeps_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('accounts:change_password'), {
            'old_password': self.password,
            'new_password1': 'Changed-book-pass-73', 'new_password2': 'Changed-book-pass-73',
        })
        self.assertRedirects(response, reverse('books:index'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed-book-pass-73'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)
        self.assertEqual(self.client.get(reverse('accounts:update')).status_code, 200)

    def test_authenticated_forms_and_account_deletion(self):
        self.client.force_login(self.user)
        for name in ['update', 'change_password']:
            self.assertEqual(self.client.get(reverse('accounts:' + name)).status_code, 200)
            self.assertEqual(self.client.put(reverse('accounts:' + name)).status_code, 405)
        self.assertEqual(self.client.get(reverse('accounts:profile', args=['reader'])).status_code, 200)
        self.assertEqual(self.client.get(reverse('accounts:profile', args=['missing'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('accounts:delete')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('accounts:delete')), reverse('books:index'))
        self.assertFalse(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_reading_profile_signup_edit_initial_and_display(self):
        response = self.client.post(reverse('accounts:signup'), {
            'username': 'booklover', 'email': 'book@example.com',
            'last_name': '김', 'first_name': '독서', 'password1': self.password,
            'password2': self.password, 'gender': 'F', 'age': 25,
            'weekly_reading_hours': 7, 'annual_reading_count': 30,
            'interested_genres': ['NOVEL', 'SCIENCE'],
        })
        self.assertRedirects(response, reverse('books:index'))
        user = get_user_model().objects.get(username='booklover')
        self.assertEqual(user.interested_genres, 'NOVEL,SCIENCE')
        self.assertEqual((user.age, user.weekly_reading_hours, user.annual_reading_count), (25, 7, 30))
        response = self.client.get(reverse('accounts:update'))
        self.assertEqual(response.context['form'].initial['interested_genres'], ['NOVEL', 'SCIENCE'])
        response = self.client.get(reverse('accounts:profile', args=['booklover']))
        for text in ['김독서', 'book@example.com', '여성', '25', '7시간', '30권', '소설, 과학']:
            self.assertContains(response, text)
        response = self.client.post(reverse('accounts:update'), {
            'gender': 'M', 'age': 26, 'weekly_reading_hours': 8,
            'annual_reading_count': 40, 'interested_genres': ['HISTORY'],
        })
        self.assertRedirects(response, reverse('books:index'))
        user.refresh_from_db()
        self.assertEqual(user.interested_genres, 'HISTORY')
        self.assertEqual(user.age, 26)
        self.client.post(reverse('accounts:update'), {})
        user.refresh_from_db()
        self.assertEqual(user.interested_genres, '')

    def test_reading_profile_rejects_non_positive_and_unknown_genres(self):
        from .forms import CustomUserChangeForm

        for field in ['age', 'weekly_reading_hours', 'annual_reading_count']:
            for value in [0, -1, '1.5', 'invalid']:
                form = CustomUserChangeForm({field: value}, instance=self.user)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
        form = CustomUserChangeForm({'interested_genres': ['UNKNOWN']}, instance=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('interested_genres', form.errors)
