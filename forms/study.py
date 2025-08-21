from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, NumberRange, ValidationError

class Step1aBasicDetailsForm(FlaskForm):
    """Step 1a: Basic Study Details Form."""
    title = StringField('Study Title', validators=[
        DataRequired(message='Study title is required'),
        Length(min=5, max=200, message='Title must be between 5 and 200 characters')
    ])
    background = TextAreaField('Study Background', validators=[
        DataRequired(message='Study background is required'),
        Length(min=20, max=1000, message='Background must be between 20 and 1000 characters')
    ])
    language = SelectField('Language', choices=[
        ('en', 'English'),
        ('es', 'Spanish'),
        ('fr', 'French'),
        ('de', 'German'),
        ('it', 'Italian'),
        ('pt', 'Portuguese'),
        ('ru', 'Russian'),
        ('zh', 'Chinese'),
        ('ja', 'Japanese'),
        ('ko', 'Korean')
    ], validators=[DataRequired(message='Language selection is required')])
    terms_accepted = BooleanField('I accept the terms and conditions', validators=[
        DataRequired(message='You must accept the terms and conditions')
    ])
    submit = SubmitField('Continue to Study Type')

class Step1bStudyTypeForm(FlaskForm):
    """Step 1b: Study Type & Main Question Form."""
    study_type = SelectField('Study Type', choices=[
        ('grid', 'Grid Study - Image/Text Elements'),
        ('layer', 'Layer Study - Categorized Elements (A, B, C, D)')
    ], validators=[DataRequired(message='Study type selection is required')])
    main_question = TextAreaField('Main Research Question', validators=[
        DataRequired(message='Main research question is required'),
        Length(min=10, max=500, message='Question must be between 10 and 500 characters')
    ])
    orientation_text = TextAreaField('Orientation Text for Respondents', validators=[
        DataRequired(message='Orientation text is required'),
        Length(min=20, max=1000, message='Orientation text must be between 20 and 1000 characters')
    ])
    submit = SubmitField('Continue to Rating Scale')

class Step1cRatingScaleForm(FlaskForm):
    """Step 1c: Rating Scale Configuration Form."""
    min_value = IntegerField('Minimum Value', validators=[
        DataRequired(message='Minimum value is required'),
        NumberRange(min=1, max=10, message='Minimum value must be between 1 and 10')
    ])
    max_value = IntegerField('Maximum Value', validators=[
        DataRequired(message='Maximum value is required'),
        NumberRange(min=1, max=10, message='Maximum value must be between 1 and 10')
    ])
    min_label = StringField('Minimum Label', validators=[
        DataRequired(message='Minimum label is required'),
        Length(max=100, message='Label must be 100 characters or less')
    ])
    max_label = StringField('Maximum Label', validators=[
        DataRequired(message='Maximum label is required'),
        Length(max=100, message='Label must be 100 characters or less')
    ])
    middle_label = StringField('Middle Label (Optional)', validators=[
        Length(max=100, message='Label must be 100 characters or less')
    ])
    submit = SubmitField('Continue to Study Elements')
    
    def validate_max_value(self, max_value):
        """Ensure max_value is greater than min_value."""
        if self.min_value.data and max_value.data <= self.min_value.data:
            raise ValidationError('Maximum value must be greater than minimum value.')

class Step2cIPEDParametersForm(FlaskForm):
    """Step 2c: IPED Parameters Form."""
    num_elements = IntegerField('Number of Elements', validators=[
        DataRequired(message='Number of elements is required'),
        NumberRange(min=4, max=16, message='Number of elements must be between 4 and 16')
    ])
    tasks_per_consumer = IntegerField('Tasks per Consumer', validators=[
        DataRequired(message='Tasks per consumer is required'),
        NumberRange(min=1, max=100, message='Tasks per consumer must be between 1 and 100')
    ])
    number_of_respondents = IntegerField('Number of Respondents', validators=[
        DataRequired(message='Number of respondents is required'),
        NumberRange(min=1, max=10000, message='Number of respondents must be between 1 and 10,000')
    ])
    min_active_elements = IntegerField('Minimum Active Elements per Task', validators=[
        DataRequired(message='Minimum active elements is required'),
        NumberRange(min=1, max=20, message='Minimum active elements must be between 1 and 20')
    ])
    max_active_elements = IntegerField('Maximum Active Elements per Task', validators=[
        DataRequired(message='Maximum active elements is required'),
        NumberRange(min=1, max=20, message='Maximum active elements must be between 1 and 20')
    ])
    submit = SubmitField('Continue to Task Generation')
    
    def validate_max_active_elements(self, max_active_elements):
        """Ensure max_active_elements is greater than min_active_elements."""
        if self.min_active_elements.data and max_active_elements.data <= self.min_active_elements.data:
            raise ValidationError('Maximum active elements must be greater than minimum active elements.')
    
    def validate_min_active_elements(self, min_active_elements):
        """Ensure min_active_elements is less than or equal to num_elements."""
        if self.num_elements.data and min_active_elements.data > self.num_elements.data:
            raise ValidationError('Minimum active elements cannot exceed the total number of elements.')

class Step3aTaskGenerationForm(FlaskForm):
    """Step 3a: IPED Task Matrix Generation Form."""
    regenerate_matrix = BooleanField('Regenerate Task Matrix with Different Seed')
    submit = SubmitField('Generate Task Matrix')

class Step3bLaunchForm(FlaskForm):
    """Step 3b: Study Preview & Launch Form."""
    launch_study = BooleanField('I am ready to launch this study')
    submit = SubmitField('Launch Study')

class LayerStudyCategoryForm(FlaskForm):
    """Form for configuring layer study categories."""
    num_categories = IntegerField('Number of Categories', validators=[
        DataRequired(message='Number of categories is required'),
        NumberRange(min=2, max=10, message='Number of categories must be between 2 and 10')
    ])
    submit = SubmitField('Continue to Category Setup')
