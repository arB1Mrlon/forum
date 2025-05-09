# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from config import Config
from extensions import db

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def allowed_file(filename):
    """Проверяет, что файл имеет разрешенное расширение"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Импортируем модели после инициализации db
with app.app_context():
    from models import User, Category, Post, Comment, Rating
    db.create_all()
    
    # Создаем администратора и категории по умолчанию
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password_hash=generate_password_hash('not_admin'),
            is_admin=True
        )
        db.session.add(admin)
        
        categories = ['Общие обсуждения', 'Учеба', 'Школьные новости', 'Хобби']
        for name in categories:
            if not Category.query.filter_by(name=name).first():
                category = Category(name=name, description=f'Обсуждения на тему {name.lower()}')
                db.session.add(category)
        
        db.session.commit()

# ... остальные маршруты и функции остаются без изменений ...

# Главная страница
@app.route('/')
def index():
    categories = Category.query.all()
    pinned_posts = Post.query.filter_by(is_pinned=True).order_by(Post.created_at.desc()).all()
    recent_posts = Post.query.filter_by(is_pinned=False).order_by(Post.created_at.desc()).limit(10).all()
    return render_template('index.html', categories=categories, pinned_posts=pinned_posts, recent_posts=recent_posts)

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято!', 'error')
        else:
            user = User(
                username=username,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            flash('Вы успешно вошли!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль!', 'error')
    
    return render_template('login.html')

# Выход
@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('is_admin', None)
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

# Просмотр категории
@app.route('/category/<int:category_id>')
def view_category(category_id):
    category = Category.query.get_or_404(category_id)
    posts = Post.query.filter_by(category_id=category_id).order_by(Post.created_at.desc()).all()
    return render_template('categories.html', category=category, posts=posts)

# Создание поста
@app.route('/create_post', methods=['GET', 'POST'])
def create_post():
    if 'username' not in session:
        flash('Войдите, чтобы создать пост!', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        category_id = request.form['category_id']
        
        # Обработка загрузки изображения
        image = None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename
        
        user = User.query.filter_by(username=session['username']).first()
        
        post = Post(
            title=title,
            content=content,
            user_id=user.id,
            category_id=category_id,
            image=image
        )
        
        db.session.add(post)
        db.session.commit()
        flash('Пост успешно создан!', 'success')
        return redirect(url_for('view_post', post_id=post.id))
    
    categories = Category.query.all()
    return render_template('create_post.html', categories=categories)

# Просмотр поста
@app.route('/post/<int:post_id>', methods=['GET', 'POST'])
def view_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if request.method == 'POST':
        if 'username' not in session:
            flash('Войдите, чтобы оставить комментарий!', 'error')
            return redirect(url_for('login'))
        
        content = request.form['content']
        user = User.query.filter_by(username=session['username']).first()
        
        comment = Comment(
            content=content,
            user_id=user.id,
            post_id=post.id
        )
        
        db.session.add(comment)
        db.session.commit()
        flash('Комментарий добавлен!', 'success')
        return redirect(url_for('view_post', post_id=post.id))
    
    return render_template('post.html', post=post)

# Редактирование поста
@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if 'username' not in session:
        flash('Войдите, чтобы редактировать пост!', 'error')
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['username']).first()
    
    if user.id != post.user_id and not session.get('is_admin'):
        flash('У вас нет прав редактировать этот пост!', 'error')
        return redirect(url_for('view_post', post_id=post.id))
    
    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        post.category_id = request.form['category_id']
        
        # Обработка загрузки изображения
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                # Удаляем старое изображение, если есть
                if post.image:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], post.image))
                    except OSError:
                        pass
                
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                post.image = filename
        
        db.session.commit()
        flash('Пост успешно обновлен!', 'success')
        return redirect(url_for('view_post', post_id=post.id))
    
    categories = Category.query.all()
    return render_template('create_post.html', post=post, categories=categories, edit_mode=True)

# Удаление поста
@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    if 'username' not in session:
        flash('Войдите, чтобы удалить пост!', 'error')
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['username']).first()
    
    if user.id != post.user_id and not session.get('is_admin'):
        flash('У вас нет прав удалить этот пост!', 'error')
        return redirect(url_for('view_post', post_id=post.id))
    
    try:
        # Удаляем все комментарии к посту
        Comment.query.filter_by(post_id=post.id).delete()
        
        # Удаляем все оценки поста
        Rating.query.filter_by(post_id=post.id).delete()
        
        # Удаляем изображение, если есть
        if post.image:
            try:
                os.remove(os.path.join(app.config['UPLOAD_FOLDER'], post.image))
            except OSError:
                pass
        
        # Удаляем сам пост
        db.session.delete(post)
        db.session.commit()
        flash('Пост успешно удален!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении поста: {str(e)}', 'error')
    
    return redirect(url_for('index'))

# Оценка поста (лайк/дизлайк)
@app.route('/rate_post/<int:post_id>/<int:value>', methods=['POST'])
def rate_post(post_id, value):
    if 'username' not in session:
        flash('Войдите, чтобы оценить пост!', 'error')
        return redirect(url_for('login'))
    
    post = Post.query.get_or_404(post_id)
    user = User.query.filter_by(username=session['username']).first()
    
    # Проверяем, не оценивал ли уже пользователь этот пост
    existing_rating = Rating.query.filter_by(user_id=user.id, post_id=post.id).first()
    
    if existing_rating:
        if existing_rating.value == value:
            # Удаляем оценку, если пользователь нажимает на ту же кнопку
            db.session.delete(existing_rating)
            db.session.commit()
            flash('Ваша оценка удалена!', 'info')
        else:
            # Изменяем оценку
            existing_rating.value = value
            db.session.commit()
            flash('Ваша оценка изменена!', 'info')
    else:
        # Добавляем новую оценку
        rating = Rating(
            value=value,
            user_id=user.id,
            post_id=post.id
        )
        db.session.add(rating)
        db.session.commit()
        flash('Спасибо за вашу оценку!', 'success')
    
    return redirect(url_for('view_post', post_id=post.id))

# Поиск по форуму
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    
    if not query:
        flash('Введите поисковый запрос!', 'error')
        return redirect(url_for('index'))
    
    posts = Post.query.filter(
        (Post.title.contains(query)) | (Post.content.contains(query))
    ).order_by(Post.created_at.desc()).all()
    
    return render_template('search.html', query=query, posts=posts)

# Панель администратора
@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if 'username' not in session or not session.get('is_admin'):
        abort(403)
    
    if request.method == 'POST':
        action = request.form['action']
        
        if action == 'pin_post':
            post_id = request.form['post_id']
            post = Post.query.get(post_id)
            post.is_pinned = True
            db.session.commit()
            flash('Пост закреплен!', 'success')
        
        elif action == 'unpin_post':
            post_id = request.form['post_id']
            post = Post.query.get(post_id)
            post.is_pinned = False
            db.session.commit()
            flash('Пост откреплен!', 'info')
        
        elif action == 'close_post':
            post_id = request.form['post_id']
            post = Post.query.get(post_id)
            post.is_closed = True
            db.session.commit()
            flash('Обсуждение закрыто!', 'success')
        
        elif action == 'open_post':
            post_id = request.form['post_id']
            post = Post.query.get(post_id)
            post.is_closed = False
            db.session.commit()
            flash('Обсуждение открыто!', 'info')
        
        elif action == 'add_category':
            name = request.form['name']
            description = request.form['description']
            
            if Category.query.filter_by(name=name).first():
                flash('Категория с таким именем уже существует!', 'error')
            else:
                category = Category(name=name, description=description)
                db.session.add(category)
                db.session.commit()
                flash('Категория добавлена!', 'success')
    
    posts = Post.query.order_by(Post.created_at.desc()).all()
    categories = Category.query.all()
    return render_template('admin.html', posts=posts, categories=categories)

if __name__ == '__main__':
    app.run(debug=True)