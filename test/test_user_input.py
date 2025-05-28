def test_send_user_input_missing_field(client):
    response = client.post('/send-user-input', data={})
    assert response.status_code == 400
    assert 'error' in response.get_json()

# Use this if you want to mock successful behavior:
# def test_send_user_input_success(client, monkeypatch):
#     def mock_generate_user_response(user_input):
#         return "Mock response"
#     from server.services import user_input_service
#     monkeypatch.setattr(user_input_service, "generate_user_response", mock_generate_user_response)
#     response = client.post('/send-user-input', data={'user_input': 'Test'})
#     assert response.status_code == 200
#     assert response.get_json()['response'] == 'Mock response'
