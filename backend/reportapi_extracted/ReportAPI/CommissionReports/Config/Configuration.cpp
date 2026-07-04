//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "..\stdafx.h"
#include "Configuration.h"

//---
CConfiguration ExtConfig;
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CConfiguration::CConfiguration() : m_commissions(NULL),m_commissions_total(0)
  {
//---
//---
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CConfiguration::~CConfiguration()
  {
//--- удалим все нафих
   if(m_commissions!=NULL)
     {
      delete[] m_commissions;
      m_commissions=NULL;
     }
//--- занулим количество
   m_commissions_total=0;
//---
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CConfiguration::Reload(ConGroup *groups,const int groups_total,ConSymbol *symbols,const int symbols_total)
  {
   int         commissions_max=m_commissions_total;
   FILE       *file;
   char        buffer[512],*cp;
   Commission *temp;
   ConGroup   *group;
   ConSymbol  *symbol;
//--- прежде всего закроем все
   m_commissions_total=0;
//--- проверки
   if(groups==NULL || groups_total<0 || symbols==NULL || symbols_total<0) return(FALSE);
//--- проверим и создадим в случае чего директорию конфиг в папке менеджера
   StringCchPrintfA(buffer,sizeof(buffer)-1,"%s\\config",ExtProgramPath);
   if(GetFileAttributes(buffer)==INVALID_FILE_ATTRIBUTES) CreateDirectory(buffer,NULL);
//--- откроем файл
   StringCchPrintfA(buffer,sizeof(buffer)-1,"%s\\config\\CommissionReports.ini",ExtProgramPath);
   if((file=fopen(buffer,"rt+"))==NULL)
     {
      //--- пробуем создать файл
      if((file=fopen(buffer,"wt"))==NULL) return(FALSE);
      //--- понапишем туда комментов
      fprintf(file,"\n; Commission Reports Configuration File\n\n");
      //--- сделаем заготовку
      for(group=groups;group<groups+groups_total;group++)
        {
         //--- выведем для группы инструменты
         for(symbol=symbols;symbol<symbols+symbols_total;symbol++)
            fprintf(file,"%s_%s=0.0\n",group->group,symbol->symbol);
         //---
         fprintf(file,"\n");
        }
      //--- закроем все
      fclose(file);
      //--- хотя ничего не загрузили, но файл создали
      return(TRUE);
     }
//--- читаем настройки
   while(fgets(buffer,sizeof(buffer)-1,file)!=NULL)
     {
      //--- подготовимся
      TERMINATE_STR(buffer); ClearLF(buffer);
      if(buffer[0]==0 || buffer[0]==';') continue;
      //--- вычитываем параметр
      if((cp=strchr(buffer,'='))==NULL)  continue;
      *cp++=0;
      //--- проверим есть куда вставить
      if(m_commissions==NULL || m_commissions_total>=commissions_max)
        {
         //--- выделим темповый буфер побольше
         if((temp=new(std::nothrow) Commission[commissions_max+1024])==NULL)
            return(FALSE);
         //--- копируем туда все что есть
         if(m_commissions!=NULL && m_commissions_total>0)
           {
            memcpy(temp,m_commissions,sizeof(Commission)*m_commissions_total);
            delete[] m_commissions;
           }
         //--- заменяем на новый буфер
         commissions_max=commissions_max+1024;
         m_commissions  =temp;
        }
      //--- все можно вставить
      COPY_STR(m_commissions[m_commissions_total].group_symbol,buffer);
      m_commissions[m_commissions_total].commission=atof(cp);
      m_commissions_total++;
     }
//--- закроем файл
   fclose(file);
//--- все пучком
   return(TRUE);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double CConfiguration::GetCommission(const char *group,const char *symbol)
  {
   char  tmp[128];
   int   i;
//--- проверки
   if(group==NULL || symbol==NULL || m_commissions==NULL || m_commissions_total<1)
      return(0);
//--- сформируем ключ
   StringCchPrintfA(tmp,sizeof(tmp)-1,"%s_%s",group,symbol);
//--- пытаемся найти
   for(i=0;i<m_commissions_total;i++)
      if(_stricmp(tmp,m_commissions[i].group_symbol)==0)
         return(m_commissions[i].commission);
//--- ну типа не нашли значит нет там ничего
   return(0);
  }
//+------------------------------------------------------------------+

