from django.shortcuts import render, get_object_or_404
from .models import Article

def home(request):
	featured = Article.objects.filter(is_featured=True).order_by('-published_at')[:5]
	latest = Article.objects.order_by('-published_at')[:10]
	return render(request, 'news/home.html', {
		'featured': featured,
		'latest': latest,
	})

def article_detail(request, slug):
	article = get_object_or_404(Article, slug=slug)
	return render(request, 'news/article_detail.html', {
		'article': article,
	})

def archive(request):
	articles = Article.objects.order_by('-published_at')
	return render(request, 'news/archive.html', {
		'articles': articles,
	})

# BBC-style category views
def category_view(request, category):
	# Normalize category to match model choices
	category_map = {
		'world': 'World',
		'uk': 'UK',
		'business': 'Business',
		'politics': 'Politics',
		'health': 'Health',
		'science': 'Science',
		'technology': 'Technology',
		'entertainment': 'Entertainment',
		'sport': 'Sport',
	}
	cat_label = category_map.get(category.lower())
	if not cat_label:
		return render(request, 'news/category.html', {
			'category': category,
			'articles': [],
			'invalid': True,
		})
	articles = Article.objects.filter(category=cat_label).order_by('-published_at')
	return render(request, 'news/category.html', {
		'category': cat_label,
		'articles': articles,
		'invalid': False,
	})
