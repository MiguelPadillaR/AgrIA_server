def test_hello_world(client):
    response = client.get('/hello-world')
    assert response.status_code == 200
    assert response.get_json() == "Hello world!"
