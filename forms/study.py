from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, IntegerField, BooleanField, SubmitField, FloatField
from wtforms.validators import DataRequired, Email, Length, NumberRange, ValidationError, Optional

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
        ('grid', 'Grid Study (Side-by-Side)'),
        ('layer', 'Layer Study (Stacked)')
    ], validators=[DataRequired(message='Study type selection is required')])
    main_question = TextAreaField('Main Task Question', validators=[
        DataRequired(message='Main Task Question is required'),
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
        NumberRange(min=1, max=5, message='Minimum value must be between 1 and 10')
    ])
    max_value = IntegerField('Maximum Value', validators=[
        DataRequired(message='Maximum value is required'),
        NumberRange(min=2, max=5, message='Maximum value must be between 1 and 5')
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
    """Step 2c: IPED Parameters Form for Grid Studies."""
    number_of_respondents = IntegerField('Number of Respondents', validators=[
        DataRequired(message='Number of respondents is required'),
        NumberRange(min=1, max=10000, message='Number of respondents must be between 1 and 10,000')
    ])
    submit = SubmitField('Continue to Task Generation')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These will be auto-calculated or use defaults from the script
        self.num_elements = None  # Will come from step2a
        self.tasks_per_consumer = None  # Will be auto-calculated
        self.exposure_tolerance_cv = 1.0  # Default from script
        self.seed = None  # Optional, will use None if not provided

class LayerConfigForm(FlaskForm):
    """Form for configuring layers in a layer study (without IPED parameters)."""
    default_background = FileField('Default Background (Optional)', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Only image files are allowed!')
    ])
    submit = SubmitField('Save Layers & Continue')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These will be auto-calculated
        self.tasks_per_consumer = None
        self.total_layers = None

class LayerIPEDForm(FlaskForm):
    """Form for IPED parameters after layers are configured."""
    number_of_respondents = IntegerField('Number of Respondents', validators=[
        DataRequired(message='Number of respondents is required'),
        NumberRange(min=1, max=10000, message='Number of respondents must be between 1 and 10,000')
    ])
    # Exposure tolerance is fixed at 2.0% as per original layers_config.py logic
    # Random seed is not used in original logic
    submit = SubmitField('Generate Tasks')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These will be auto-calculated
        self.tasks_per_consumer = None
        self.total_layers = None

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
        NumberRange(min=3, max=10, message='Number of categories must be between 3 and 10')
    ])
    submit = SubmitField('Continue to Category Setup')

class GridCategoryForm(FlaskForm):
    """Form for configuring grid study categories."""
    num_categories = IntegerField('Number of Categories', validators=[
        DataRequired(message='Number of categories is required'),
        NumberRange(min=3, max=10, message='Number of categories must be between 3 and 10')
    ])
    submit = SubmitField('Continue to Category Setup')

class GridConfigForm(FlaskForm):
    """Form for configuring grid study categories and elements (without IPED parameters)."""
    submit = SubmitField('Save Categories & Continue')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These will be auto-calculated
        self.tasks_per_consumer = None
        self.total_categories = None

class GridIPEDForm(FlaskForm):
    """Form for IPED parameters after grid categories are configured."""
    number_of_respondents = IntegerField('Number of Respondents', validators=[
        DataRequired(message='Number of respondents is required'),
        NumberRange(min=1, max=10000, message='Number of respondents must be between 1 and 10,000')
    ])
    # Exposure tolerance is fixed at 1.0% as per original grid logic
    # Random seed is optional
    submit = SubmitField('Generate Tasks')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These will be auto-calculated
        self.tasks_per_consumer = None
        self.total_categories = None
