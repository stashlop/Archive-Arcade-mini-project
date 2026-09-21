import io

def test_max_content_length_configured(app):
    assert app.config['MAX_CONTENT_LENGTH'] == 16 * 1024 * 1024

def test_invalid_upload_signature(auth_client):
    # Fake file claiming to be PNG but containing arbitrary text
    fake_png = (io.BytesIO(b'this is not a valid png file'), 'test.png')
    res = auth_client.post('/community/profile', data={
        'photo': fake_png
    }, content_type='multipart/form-data')
    # Should reject with 400 or 403 (needs community email or invalid content)
    assert res.status_code in (400, 403)
