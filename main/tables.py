import django_tables2 as tables
from django_tables2 import A
from django.utils.html import format_html
from .models import UserProfile


class ClientTable(tables.Table):
    name = tables.Column(
        linkify=('profile', {'pk': A('id')}),
        orderable=True,
        attrs={
            'td': {'class': 'px-6 py-4 whitespace-nowrap'},
            'th': {'class': 'px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider'}
        }
    )
    email = tables.Column(
        orderable=True,
        attrs={
            'td': {'class': 'px-6 py-4 whitespace-nowrap'},
            'th': {'class': 'px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider'}
        }
    )
    phone = tables.Column(
        orderable=True,
        attrs={
            'td': {'class': 'px-6 py-4 whitespace-nowrap'},
            'th': {'class': 'px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider'}
        }
    )
    status = tables.Column(
        orderable=True,
        attrs={
            'td': {'class': 'px-6 py-4 whitespace-nowrap'},
            'th': {'class': 'px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider'}
        }
    )
    actions = tables.Column(
        empty_values=(),
        orderable=False,
        attrs={
            'td': {'class': 'px-6 py-4 whitespace-nowrap text-right text-sm font-medium'},
            'th': {'class': 'px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider'}
        }
    )

    class Meta:
        model = UserProfile
        template_name = "django_tables2/bootstrap4.html"
        fields = ('name', 'email', 'phone', 'status', 'actions')
        attrs = {
            'class': 'min-w-full divide-y divide-gray-200',
            'thead': {'class': 'bg-gray-50'},
            'tbody': {'class': 'bg-white divide-y divide-gray-200'}
        }
        empty_text = "No clients found"
        per_page = 25

    def render_status(self, value, record):
        """Render status with appropriate styling"""
        if record.is_active:
            return format_html(
                '<span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">{}</span>',
                record.status.title() if record.status else 'Active'
            )
        else:
            return format_html(
                '<span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">{}</span>',
                record.status.title() if record.status else 'Inactive'
            )

    def render_actions(self, record):
        """Render action buttons"""
        return format_html(
            '''
            <button type="button" class="edit-btn text-blue-600 hover:text-blue-800 mr-2" data-id="{}">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
            </button>
            <button type="button" class="delete-btn text-red-600 hover:text-red-800 mr-2" data-id="{}">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
            </button>
            ''',
            record.id, record.id
        ) 