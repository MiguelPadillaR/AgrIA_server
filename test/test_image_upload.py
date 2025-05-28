def test_send_image_missing_file(client):
    response = client.post('/send-image', data={})
    assert response.status_code == 400
    assert 'error' in response.get_json()
