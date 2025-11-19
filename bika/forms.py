from django import forms
from .models import ContactMessage
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import ContactMessage, Product, ProductCategory, CustomUser, ProductImage, ProductReview


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your.email@example.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Phone Number'
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subject of your message'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Your message...',
                'rows': 5
            }),
        }
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not phone.replace(' ', '').replace('-', '').replace('+', '').isdigit():
            raise forms.ValidationError("Please enter a valid phone number.")
        return phone

class NewsletterForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
    )


User = get_user_model()

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True, 
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your email address'
        })
    )
    first_name = forms.CharField(
        max_length=30, 
        required=True, 
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'First Name'
        })
    )
    last_name = forms.CharField(
        max_length=30, 
        required=True, 
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Last Name'
        })
    )
    phone = forms.CharField(
        max_length=20, 
        required=False, 
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Phone Number'
        })
    )
    user_type = forms.ChoiceField(
        choices=CustomUser.USER_TYPE_CHOICES, 
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'user_type', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Style the existing fields
        self.fields['username'].widget.attrs.update({
            'class': 'form-control', 
            'placeholder': 'Choose a username'
        })
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control', 
            'placeholder': 'Create a password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control', 
            'placeholder': 'Confirm password'
        })
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data['phone']
        user.user_type = self.cleaned_data['user_type']
        if commit:
            user.save()
        return user

class VendorRegistrationForm(CustomUserCreationForm):
    business_name = forms.CharField(
        max_length=200, 
        required=True, 
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your Business Name'
        })
    )
    business_description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Describe your business',
            'rows': 3
        }), 
        required=False
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'business_name', 'business_description', 'password1', 'password2')
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'vendor'
        user.business_name = self.cleaned_data['business_name']
        user.business_description = self.cleaned_data['business_description']
        if commit:
            user.save()
        return user

class CustomerRegistrationForm(CustomUserCreationForm):
    agree_terms = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove user_type field for customer registration
        del self.fields['user_type']
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.user_type = 'customer'
        if commit:
            user.save()
        return user

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()  # This will use CustomUser
        fields = ('first_name', 'last_name', 'email', 'phone', 'company', 'address', 'profile_picture')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'company': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
        }

class VendorProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()  # This will use CustomUser
        fields = ('first_name', 'last_name', 'email', 'phone', 'business_name', 'business_description', 'business_logo')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'business_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'business_logo': forms.FileInput(attrs={'class': 'form-control'}),
        }
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'slug', 'sku', 'category', 'description', 'short_description', 'tags',
            'price', 'compare_price', 'cost_price', 'tax_rate',
            'stock_quantity', 'low_stock_threshold', 'track_inventory', 'allow_backorders',
            'brand', 'model', 'weight', 'dimensions', 'color', 'size', 'material',
            'status', 'condition', 'is_featured', 'is_digital',
            'meta_title', 'meta_description'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Product Name'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'product-slug'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU001'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Detailed product description'}),
            'short_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Brief product description'}),
            'tags': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'tag1, tag2, tag3'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'compare_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'cost_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'stock_quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '5'}),
            'track_inventory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allow_backorders': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Brand Name'}),
            'model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Model Number'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Weight in kg'}),
            'dimensions': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '10x5x2'}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Red, Blue, etc.'}),
            'size': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'S, M, L, XL'}),
            'material': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cotton, Plastic, etc.'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_digital': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'meta_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SEO Meta Title'}),
            'meta_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'SEO Meta Description'}),
        }
    
    def clean_sku(self):
        sku = self.cleaned_data.get('sku')
        if sku and Product.objects.filter(sku=sku).exclude(pk=self.instance.pk).exists():
            raise ValidationError("A product with this SKU already exists.")
        return sku
    
    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price and price < 0:
            raise ValidationError("Price cannot be negative.")
        return price
    
    def clean_compare_price(self):
        compare_price = self.cleaned_data.get('compare_price')
        price = self.cleaned_data.get('price')
        
        if compare_price and price and compare_price <= price:
            raise ValidationError("Compare price must be greater than the current price.")
        return compare_price
    
    def clean_stock_quantity(self):
        stock_quantity = self.cleaned_data.get('stock_quantity')
        if stock_quantity and stock_quantity < 0:
            raise ValidationError("Stock quantity cannot be negative.")
        return stock_quantity

class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'alt_text', 'display_order', 'is_primary']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'alt_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Description of the image'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ProductImageInlineForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ['image', 'alt_text', 'display_order', 'is_primary']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'alt_text': forms.TextInput(attrs={'class': 'form-control'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class ProductReviewForm(forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ['rating', 'title', 'comment']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Review title'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Share your experience with this product'}),
        }
    
    def clean_rating(self):
        rating = self.cleaned_data.get('rating')
        if rating not in [1, 2, 3, 4, 5]:
            raise ValidationError("Please select a valid rating.")
        return rating

class ProductCategoryForm(forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ['name', 'slug', 'description', 'image', 'display_order', 'is_active', 'parent']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'parent': forms.Select(attrs={'class': 'form-control'}),
        }

class ProductSearchForm(forms.Form):
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search products...',
            'name': 'q'
        })
    )
    category = forms.ModelChoiceField(
        queryset=ProductCategory.objects.filter(is_active=True),
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    min_price = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Min Price',
            'step': '0.01'
        })
    )
    max_price = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Max Price',
            'step': '0.01'
        })
    )
    condition = forms.ChoiceField(
        choices=[('', 'Any Condition')] + Product.CONDITION_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

class ProductFilterForm(forms.Form):
    SORT_CHOICES = [
        ('newest', 'Newest First'),
        ('price_low', 'Price: Low to High'),
        ('price_high', 'Price: High to Low'),
        ('name_asc', 'Name: A to Z'),
        ('name_desc', 'Name: Z to A'),
        ('rating', 'Highest Rated'),
    ]
    
    sort_by = forms.ChoiceField(
        choices=SORT_CHOICES,
        required=False,
        initial='newest',
        widget=forms.Select(attrs={'class': 'form-control', 'onchange': 'this.form.submit()'})
    )
    in_stock = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'this.form.submit()'})
    )
    featured = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'onchange': 'this.form.submit()'})
    )

# Existing Forms (Keep these at the bottom)
class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Full Name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your.email@example.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Phone Number'
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subject of your message'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Your message...',
                'rows': 5
            }),
        }
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not phone.replace(' ', '').replace('-', '').replace('+', '').isdigit():
            raise ValidationError("Please enter a valid phone number.")
        return phone

class NewsletterForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
    )

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username or Email'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )    