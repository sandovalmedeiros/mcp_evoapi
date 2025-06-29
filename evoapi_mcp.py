from mcp.server.fastmcp import FastMCP
from group_controller import GroupController
from datetime import datetime
from send_sandeco import SendSandeco
import requests
import os
import subprocess

mcp = FastMCP("evoapi_mcp")

def compactar_video(input_path: str, output_path: str, target_crf: int = 28, resolution: str = None, bitrate: str = None):
    """
    Compacta um vídeo usando FFmpeg somente se o tamanho for maior que 200MB.
    Usa heurística automática para resolução/bitrate se não especificados.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Arquivo não encontrado: {input_path}")

    original_size = os.path.getsize(input_path)

    if original_size <= 200 * 1024 * 1024:
        return input_path  # sem compactar

    print("Compactação iniciada: vídeo maior que 200MB. Isso pode levar algum tempo...")

    if not resolution:
        if original_size > 300 * 1024 * 1024:
            resolution = "640:360"
        elif original_size > 150 * 1024 * 1024:
            resolution = "854:480"
        else:
            resolution = "1280:720"

    if not bitrate:
        bitrate = "800k" if original_size > 150 * 1024 * 1024 else "1M"

    command = [
        "ffmpeg",
        "-i", input_path,
        "-vcodec", "libx264",
        "-crf", str(target_crf),
        "-preset", "slow",
        "-vf", f"scale={resolution}",
        "-b:v", bitrate,
        output_path
    ]

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Erro ao compactar vídeo: {result.stderr}")

    if os.path.getsize(output_path) > 200 * 1024 * 1024:
        raise ValueError("Vídeo compactado ainda excede 200MB. Tente um CRF mais alto ou reduza a resolução/bitrate.")

    return output_path

def compactar_audio(input_path: str, output_path: str, bitrate: str = "96k"):
    """
    Compacta um arquivo de áudio usando FFmpeg para reduzir seu tamanho.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {input_path}")

    original_size = os.path.getsize(input_path)
    if original_size <= 160 * 1024 * 1024:
        return input_path  # sem compactar

    print("Compactação iniciada: áudio maior que 160MB. Isso pode levar algum tempo...")

    command = [
        "ffmpeg",
        "-i", input_path,
        "-b:a", bitrate,
        output_path
    ]

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Erro ao compactar áudio: {result.stderr}")

    if os.path.getsize(output_path) > 160 * 1024 * 1024:
        raise ValueError("Áudio compactado ainda excede 160MB. Tente um bitrate mais baixo.")

    return output_path

@mcp.tool(name="get_groups")
def get_groups() -> str:
    controller = GroupController()
    groups = controller.fetch_groups()
    return "\n".join([f"Grupo ID: {g.group_id}, Nome: {g.name}" for g in groups])

@mcp.tool(name="get_group_messages")
def get_group_messages(group_id: str, start_date: str, end_date: str) -> str:
    controller = GroupController()
    messages = controller.get_messages(group_id, start_date, end_date)
    formatted = []
    for msg in messages:
        formatted.append(
            f"Mensagem -----------------------------------\n"
            f"Usuário: {msg.push_name}\n"
            f"Data e hora: {datetime.fromtimestamp(msg.message_timestamp).strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"Tipo: {msg.message_type}\n"
            f"Texto: {msg.get_text()}"
        )
    return "\n".join(formatted)

def _send_message(recipient: str, message: str) -> str:
    try:
        SendSandeco().textMessage(recipient, message)
        return "Mensagem enviada com sucesso"
    except Exception as e:
        return f"Erro ao enviar mensagem: {e}"

def _send_media_message(method, recipient: str, file_path: str, caption: str = "") -> str:
    try:
        send = SendSandeco()
        getattr(send, method)(recipient, file_path, caption)
        return f"{method.capitalize()} enviado com sucesso"
    except Exception as e:
        return f"Erro ao enviar {method}: {e}"

@mcp.tool(name="send_message_to_group")
def send_message_to_group(group_id: str, message: str) -> str:
    return _send_message(group_id, message)

@mcp.tool(name="send_message_to_phone")
def send_message_to_phone(cellphone: str, message: str) -> str:
    return _send_message(cellphone, message)

@mcp.tool(name="send_image")
def send_image(recipient: str, image_path: str, caption: str = "") -> str:
    return _send_media_message("image", recipient, image_path, caption)

@mcp.tool(name="send_audio")
def send_audio(recipient: str, audio_path: str, caption: str = "") -> str:
    try:
        temp_path = os.path.join(os.path.dirname(audio_path), "audio_compactado.mp3")
        compactado = compactar_audio(audio_path, temp_path)
        return _send_media_message("audio", recipient, compactado, caption)
    except Exception as e:
        return f"Erro ao enviar áudio: {e}"

@mcp.tool(name="send_video")
def send_video(recipient: str, video_path: str, caption: str = "", crf: int = 28, resolution: str = None, bitrate: str = None) -> str:
    try:
        temp_path = os.path.join(os.path.dirname(video_path), "video_compactado.mp4")
        compactado = compactar_video(video_path, temp_path, crf, resolution, bitrate)
        return _send_media_message("video", recipient, compactado, caption)
    except Exception as e:
        return f"Erro ao processar/enviar vídeo: {e}"

@mcp.tool(name="send_document")
def send_document(recipient: str, document_path: str, caption: str = "") -> str:
    return _send_media_message("document", recipient, document_path, caption)

@mcp.tool(name="send_pdf")
def send_pdf(recipient: str, pdf_path: str, caption: str = "") -> str:
    return _send_media_message("PDF", recipient, pdf_path, caption)

@mcp.tool(name="catalogar_qas")
def catalogar_qas(group_id: str, start_date: str, end_date: str) -> str:
    try:
        resumo = get_group_messages(group_id, start_date, end_date)
        response = requests.post("http://localhost:8000/analisar", json={"grupo": group_id, "resumo": resumo}, timeout=30)
        response.raise_for_status()
        return f"✅ {response.json().get('qtd', 0)} perguntas/respostas extraídas e salvas com sucesso."
    except Exception as e:
        return f"❌ Erro ao catalogar Q&As: {str(e)}"

@mcp.tool(name="buscar_qas")
def buscar_qas(consulta: str, top_k: int = 3) -> str:
    try:
        response = requests.post("http://localhost:8000/buscar", json={"consulta": consulta, "top_k": top_k})
        response.raise_for_status()
        resultados = response.json()
        return "\n".join([f"P: {r['pergunta']}\nR: {r['respostas'][0]}" for r in resultados]) or "Nenhum resultado encontrado."
    except Exception as e:
        return f"Erro na busca semântica: {e}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
