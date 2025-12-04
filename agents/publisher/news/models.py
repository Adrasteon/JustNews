from django.db import models

from django.db import models

class Article(models.Model):
	title = models.CharField(max_length=200)
	slug = models.SlugField(unique=True)
	summary = models.TextField()
	body = models.TextField()
	published_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	author = models.CharField(max_length=100)
	score = models.FloatField(help_text="Editorial score (accuracy, trust)")
	evidence = models.TextField(help_text="Supporting evidence, sources, fact-checks")
	is_featured = models.BooleanField(default=False)
	CATEGORY_CHOICES = [
		("world", "World"),
		("uk", "UK"),
		("business", "Business"),
		("politics", "Politics"),
		("health", "Health"),
		("science", "Science"),
		("technology", "Tech"),
		("entertainment", "Entertainment"),
		("sport", "Sport"),
	]
	category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="world")

	class Meta:
		ordering = ['-published_at']

	def __str__(self):
		return self.title
# Create your models here.
