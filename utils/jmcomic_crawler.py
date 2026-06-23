"""
Author: zhouyuchong
Date: 2025-08-04 11:00:03
Description:
LastEditors: zhouyuchong
LastEditTime: 2025-08-08 10:23:26
"""

import os
import time

import jmcomic

from .constants import JMCOMIC_OPTION, PDF_DIR


def jmcomic_crawler(jm_number, logger):
    logger.info(f"Get jm comic number: {jm_number}")

    # clean pdf in pdf dir, so we know which pdf to upload later
    delete_files_in_directory(PDF_DIR, logger)

    # init jmcomic downloader
    option = jmcomic.create_option_by_str(str(JMCOMIC_OPTION), mode="yml")
    start_time = time.time()
    jmcomic.download_album(jm_album_id=jm_number, option=option)
    end_time = time.time()
    logger.info(
        f"Finish download jm comic number: {jm_number}, total time: {end_time - start_time}s"
    )

    pdf_files = [
        file_name for file_name in os.listdir(PDF_DIR) if file_name.endswith(".pdf")
    ]
    if not pdf_files:
        raise RuntimeError(
            "JM 下载完成，但未生成 PDF 文件，请检查 img2pdf 依赖是否已安装"
        )

    return [
        {"file_name": pdf_file, "file_path": os.path.join(PDF_DIR, pdf_file)}
        for pdf_file in sorted(pdf_files)
    ]


def delete_files_in_directory(target_path, logger):
    try:
        # 确保路径存在
        if not os.path.exists(target_path):
            logger.debug(f"路径 {target_path} 不存在")
            return

        # 遍历目标路径下的所有文件
        for item in os.listdir(target_path):
            item_path = os.path.join(target_path, item)
            # 只删除文件，不删除文件夹
            if os.path.isfile(item_path):
                os.remove(item_path)
                logger.debug(f"已删除文件: {item_path}")
    except Exception as e:
        logger.warning(f"删除文件时出错: {e}")


def jm_search(tags, logger):
    client = jmcomic.JmOption.default().new_jm_client()
    search_query = ""
    for tag in tags:
        search_query += f"+{tag} "
    logger.debug(f"开始搜索: {search_query}")
    page: jmcomic.JmSearchPage = client.search_site(search_query=search_query, page=1)
    # page默认的迭代方式是page.iter_id_title()，每次迭代返回 albun_id, title
    ret_text = ""
    for album_id, title in page:
        ret_text += f"[{album_id}]: {title}\n"
    return ret_text
