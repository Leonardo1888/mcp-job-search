import httpx
import asyncio

async def extract_skills_from_document(document_text: str, confidence_threshold: float = 0.5):
    """
    Estrae competenze da un documento usando l'API Lightcast Skills
    
    Args:
        document_text : Il testo del CV/documento
        confidence_threshold: Soglia di confidenza (0.0 - 1.0)
    """
    
    url = "https://api.lightcast.io/skills/versions/latest/extract"
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": "Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6IjNDNjZCRjIzMjBGNkY4RDQ2QzJERDhCMjI0MEVGMTFENTZEQkY3MUYiLCJ0eXAiOiJKV1QiLCJ4NXQiOiJQR2FfSXlEMi1OUnNMZGl5SkE3eEhWYmI5eDgifQ.eyJuYmYiOjE3NzA0ODUyNDEsImV4cCI6MTc3MDQ4ODg0MSwiaXNzIjoiaHR0cHM6Ly9hdXRoLmVtc2ljbG91ZC5jb20iLCJhdWQiOlsiYWduaXRpbyIsImNjLWFzc2Vzc21lbnRzLWFwaSIsImJlbmNobWFyayIsImNhcmVlci1wYXRod2F5cyIsImNjLXVzLWNhcmVlcnMtYXBpLXFhIiwiY2MtdWstY2FyZWVycy1hcGkiLCJjbGFzc2lmaWNhdGlvbl9hcGkiLCJkZG4iLCJlbXNpX29wZW4iLCJlbXNpYXV0aCIsIndhcm4iLCJjYy1qb2JzLWFwaSIsImtnLXBvYyIsImNhX3Bvc3RpbmdzIiwiZ2xvYmFsX3Bvc3RpbmdzIiwidWtfcG9zdGluZ3MiLCJ1c19wb3N0aW5ncyIsImdsb2JhbF9wcm9maWxlcyIsInVrX3Byb2ZpbGVzIiwidXNfcHJvZmlsZXMiLCJjYy1wcm9ncmFtcy1hcGkiLCJwcm9qZWN0ZWQtc2tpbGwtZ3Jvd3RoIiwic2ltaWxhcml0eSIsIlNraWxscyBFeHRyYWN0b3IiLCJ0aXRsZXMiLCJ1ay1pbyIsInVzLWlvIiwiaHR0cHM6Ly9hdXRoLmVtc2ljbG91ZC5jb20vcmVzb3VyY2VzIl0sImNsaWVudF9pZCI6ImVtc2liZ19taWxhbiIsInJvbGUiOiJpby51ayIsIm5hbWUiOiJNYXVybyBQZWx1Y2NoaSIsImNvbXBhbnkiOiJFbXNpIEJ1cm5pbmcgR2xhc3MgTWlsYW4iLCJlbWFpbCI6Im1hdXJvLnBlbHVjY2hpQGVtc2liZy5jb20iLCJpYXQiOjE3NzA0ODUyNDEsInNjb3BlIjpbImNsYXNzaWZpY2F0aW9uOnF1b3RhOmxvdDp1bmxpbWl0ZWQiLCJjbGFzc2lmaWNhdGlvbjpyYXRlLWxpbWl0OjIwLzEiLCJjbGFzc2lmaWNhdGlvbjpxdW90YTpza2lsbHM6dW5saW1pdGVkIiwiY2NfYXNzZXNzbWVudHNfb3BlcmF0aW9uczpDUkVBVEUsUkVBRCxERUxFVEUiLCJjY19wcm9ncmFtc19vcGVyYXRpb25zOkNSRUFURSxSRUFELFVQREFURSxERUxFVEUiLCJ0aXRsZXM6bm9ybWFsaXplOnF1b3RhOnVubGltaXRlZCIsImF2YWlsYWJpbGl0eTpCZXRhIiwidGl0bGVzOmZ1bGxfYWNjZXNzIiwiYWduaXRpbyIsImRhdGFzZXQ6ZW1zaS4qOio6KiIsImFsbG93X2xhdGVzdCIsInBvc3RpbmdzOmNhIiwidGl0bGVzOm5vcm1hbGl6ZTpidWxrIiwicG9zdGluZ3M6dXMiLCJza2lsbHM6ZXh0cmFjdDpxdW90YTp1bmxpbWl0ZWQiLCJwb3N0aW5nczp1ayIsInBvc3RpbmdzOmdsb2JhbCIsImNvbXBhbmllczpub3JtYWxpemU6cXVvdGE6dW5saW1pdGVkIiwiY29tcGFuaWVzOm5vcm1hbGl6ZTpidWxrIiwiY29tcGFuaWVzOmZ1bGxfYWNjZXNzIiwiYmVuY2htYXJrOnN1cHBseSxkZW1hbmQsY29tcGVuc2F0aW9uLGRpdmVyc2l0eSxza2lsbHMiLCJjbGFzc2lmaWNhdGlvbjp0YXhvbm9taWVzOioiLCJjbGFzc2lmaWNhdGlvbjp1c2VyOmludGVybmFsIiwiZW1zaWJnX21pbGFuLiIsIm5hYXM6aW50ZXJuYWwiLCJhc3Nlc3NtZW50cyIsImJlbmNobWFyayIsImNhcmVlci1wYXRod2F5cyIsImNhcmVlcnMiLCJjYXJlZXJzOnVrIiwiY2xhc3NpZmljYXRpb25fYXBpIiwiZGRuIiwiZW1zaV9vcGVuIiwiZW1zaWF1dGgiLCJqb2JzIiwia2ctcG9jIiwibmFhcyIsInByb2ZpbGVzOmdsb2JhbCIsInByb2ZpbGVzOnVrIiwicHJvZmlsZXM6dXMiLCJwcm9ncmFtcyIsInByb2plY3RlZC1za2lsbC1ncm93dGgiLCJzaW1pbGFyaXR5Iiwic2tpbGxzX2V4dHJhY3RvciIsInRpdGxlcyIsInVrLWlvIiwidXMtaW8iXX0.QKdyyM8a3wcnHCecl4pJlhmPsyFC412wSvDQBKinpmuqYV_v5ix6GD8pHqaXqJTa59abA_EEEUfJpt766nArfVsbdTRH4SMx63CgK1aLGHigKkf3JfPa9tEDATS_XkJ5s-KnbVG-mrsDwMC2OFBw8FDkdeA_eILbiyKRFK0vEvnxhM7pJPTpVkx6wDPuwuzcsB2wZ7b8Q2gIsJgfsCEh0gjDGEQK424OQqHX7E5z8g3vZ6NlgMoagWROhK61GZPhqp2KUUaWhxnq55eTTKEnjHdwLYYmlG3nduW1hNJWlYiKKRHcFsPC4nO_5QEWiImBFx9bdRty3rAOFT1vWfyIJg",
    }
    
    payload = {
        "text": document_text, 
        "confidenceThreshold": confidence_threshold
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()  # Solleva eccezione se errore HTTP
        return response.json()

async def main():
    cv_text = """
    Programmo in Java, C.
    """
    
    skills = await extract_skills_from_document(cv_text, confidence_threshold=0.5)
    print(skills)

asyncio.run(main())