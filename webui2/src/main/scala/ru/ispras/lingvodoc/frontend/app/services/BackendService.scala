package ru.ispras.lingvodoc.frontend.app.services

import ru.ispras.lingvodoc.frontend.api.exceptions.BackendException
import ru.ispras.lingvodoc.frontend.app.model._
import upickle.default._

import scala.concurrent.{Future, Promise}
import ru.ispras.lingvodoc.frontend.app.utils.LingvodocExecutionContext.Implicits.executionContext
import scala.scalajs.js
import scala.scalajs.js.URIUtils._
import scala.scalajs.js.{Date, JSON}
import scala.scalajs.js.Any.fromString
import scala.util.{Failure, Success, Try}
import com.greencatsoft.angularjs._
import com.greencatsoft.angularjs.core.HttpPromise.promise2future
import com.greencatsoft.angularjs.core.{HttpService, Q}

import scala.scalajs.js.JSConverters._
import org.scalajs.dom.console
import ru.ispras.lingvodoc.frontend.app.services.LexicalEntriesType.LexicalEntriesType


object LexicalEntriesType extends Enumeration {
  type LexicalEntriesType = Value
  val Published = Value("published")
  val All = Value("all")
}


@injectable("BackendService")
class BackendService($http: HttpService, $q: Q) extends Service {

  // TODO: allow user to specify different baseUrl
  private val baseUrl = ""

  private def getMethodUrl(method: String) = {
    if (baseUrl.endsWith("/"))
      baseUrl + method
    else
      baseUrl + "/" + method
  }

  private def addUrlParameter(url: String, key: String, value: String): String = {
    val param = encodeURIComponent(key) + '=' + encodeURIComponent(value)
    if (url.contains("?"))
      url + "&" + param
    else
      url + "?" + param
  }


  /**
    * Get list of perspectives for specified dictionary
    *
    * @param dictionary
    * @return
    */
  def getDictionaryPerspectives(dictionary: Dictionary): Future[Seq[Perspective]] = {
    val p = Promise[Seq[Perspective]]()
    val url = getMethodUrl("dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" +
      encodeURIComponent(dictionary.objectId.toString) + "/perspectives")
    $http.get[js.Dynamic](url) onComplete {
      case Success(response) =>
        try {
          val perspectives = read[Seq[Perspective]](js.JSON.stringify(response.perspectives))
          p.success(perspectives)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed perspectives json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed perspectives data. Missing some " +
            "required fields: " + e.getMessage))
          case e: Throwable => p.failure(BackendException("Unexpected exception:" + e.getMessage))
        }

      case Failure(e) => p.failure(BackendException("Failed to get list of perspectives for dictionary " + dictionary
        .translationString + ": " + e.getMessage))
    }
    p.future
  }

  /**
    * Get list of dictionaries
    *
    * @param query
    * @return
    */
  def getDictionaries(query: DictionaryQuery): Future[Seq[Dictionary]] = {
    val p = Promise[Seq[Dictionary]]()

    $http.post[js.Dynamic](getMethodUrl("dictionaries"), write(query)) onComplete {
      case Success(response) =>
        try {
          val dictionaries = read[Seq[Dictionary]](js.JSON.stringify(response.dictionaries))
          p.success(dictionaries)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed dictionary json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed dictionary data. Missing some " +
            "required fields: " + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get list of dictionaries: " + e.getMessage))
    }
    p.future
  }

  /**
    * Get list of dictionaries with perspectives
    *
    * @param query
    * @return
    */
  def getDictionariesWithPerspectives(query: DictionaryQuery): Future[Seq[Dictionary]] = {
    val p = Promise[Seq[Dictionary]]()
    getDictionaries(query) onComplete {
      case Success(dictionaries) =>
        val futures = dictionaries map {
          dictionary => getDictionaryPerspectives(dictionary)
        }
        Future.sequence(futures) onComplete {
          case Success(perspectives) =>
            val g = (dictionaries, perspectives).zipped.map { (dictionary, p) =>
              dictionary.perspectives = dictionary.perspectives ++ p
              dictionary
            }
            p.success(g)
          case Failure(e) => p.failure(BackendException("Failed to get list of perspectives: " + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get list of dictionaries with perspectives: " + e
        .getMessage))
    }
    p.future
  }

  /**
    * Get language graph
    *
    * @return
    */
  def getLanguages: Future[Seq[Language]] = {
    val p = Promise[Seq[Language]]()
    $http.get[js.Dynamic](getMethodUrl("languages")) onComplete {
      case Success(response) =>
        try {
          val languages = read[Seq[Language]](js.JSON.stringify(response.languages))
          p.success(languages)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed languages json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed languages data. Missing some required" +
            " fields: " + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get list of languages: " + e.getMessage))
    }
    p.future
  }


  /**
    * Get dictionary
    *
    * @param clientId
    * @param objectId
    * @return
    */
  def getDictionary(clientId: Int, objectId: Int): Future[Dictionary] = {
    val p = Promise[Dictionary]()
    val url = "dictionary/" + encodeURIComponent(clientId.toString) + "/" + encodeURIComponent(objectId.toString)
    $http.get[js.Dynamic](getMethodUrl(url)) onComplete {
      case Success(response) =>
        try {
          p.success(read[Dictionary](js.JSON.stringify(response)))
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed dictionary json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed dictionary data. Missing some " +
            "required fields: " + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get dictionary: " + e.getMessage))
    }
    p.future
  }

  /**
    * Update dictionary properties
    *
    * @param dictionary
    * @return
    */
  def updateDictionary(dictionary: Dictionary): Future[Unit] = {
    val p = Promise[Unit]()
    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" + encodeURIComponent(dictionary
      .objectId.toString)
    $http.put(getMethodUrl(url), write(dictionary)) onComplete {
      case Success(_) => p.success(Unit)
      case Failure(e) => p.failure(BackendException("Failed to remove dictionary: " + e.getMessage))
    }
    p.future
  }

  /**
    * Remove dictionary
    *
    * @param dictionary
    * @return
    */
  def removeDictionary(dictionary: Dictionary): Future[Unit] = {
    val p = Promise[Unit]()
    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" + encodeURIComponent(dictionary
      .objectId.toString)
    $http.delete(getMethodUrl(url)) onComplete {
      case Success(_) => p.success(Unit)
      case Failure(e) => p.failure(BackendException("Failed to remove dictionary: " + e.getMessage))
    }
    p.future
  }

  /**
    * Set dictionary status
    *
    * @param dictionary
    * @param status
    */
  def setDictionaryStatus(dictionary: Dictionary, status: String): Future[Unit] = {
    val p = Promise[Unit]()
    val req = JSON.stringify(js.Dynamic.literal(status = status))
    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" + encodeURIComponent(dictionary
      .objectId.toString) + "/state"
    $http.put(getMethodUrl(url), req) onComplete {
      case Success(_) =>
        dictionary.status = status
        p.success(Unit)
      case Failure(e) => p.failure(BackendException("Failed to update dictionary status: " + e.getMessage))
    }
    p.future
  }

  /**
    * Get list of published dictionaries
    * XXX: Actually it returns a complete tree of languages
    *
    * @return
    */
  def getPublishedDictionaries: core.Promise[Seq[Language]] = {
    val defer = $q.defer[Seq[Language]]()
    val req = JSON.stringify(js.Dynamic.literal(group_by_lang = true, group_by_org = false))
    $http.post[js.Dynamic](getMethodUrl("published_dictionaries"), req) onComplete {
      case Success(response) =>
        try {
          val languages = read[Seq[Language]](js.JSON.stringify(response))
          defer.resolve(languages)
        } catch {
          case e: upickle.Invalid.Json => defer.reject("Malformed dictionary json:" + e.getMessage)
          case e: upickle.Invalid.Data => defer.reject("Malformed dictionary data. Missing some required fields: " +
            e.getMessage)
        }
      case Failure(e) => defer.reject("Failed to get list of dictionaries: " + e.getMessage)
    }
    defer.promise
  }

  // Perspectives

  /**
    * Get perspective by ids
    *
    * @param clientId
    * @param objectId
    * @return
    */
  def getPerspective(clientId: Int, objectId: Int): Future[Perspective] = {
    val p = Promise[Perspective]()
    val url = "perspective/" + encodeURIComponent(clientId.toString) + "/" + encodeURIComponent(objectId.toString)
    $http.get[js.Dynamic](getMethodUrl(url)) onComplete {
      case Success(response) =>
        try {
          p.success(read[Perspective](js.JSON.stringify(response)))
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed perspective json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed perspective data. Missing some " +
            "required fields: " + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get perspective: " + e.getMessage))
    }
    p.future
  }


  /**
    * Set perspective status
    *
    * @param dictionary
    * @param perspective
    * @param status
    * @return
    */
  def setPerspectiveStatus(dictionary: Dictionary, perspective: Perspective, status: String): Future[Unit] = {
    val p = Promise[Unit]()
    val req = JSON.stringify(js.Dynamic.literal(status = status))

    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) +
      "/" + encodeURIComponent(dictionary.objectId.toString) +
      "/perspective/" + encodeURIComponent(perspective.clientId.toString) +
      "/" + encodeURIComponent(perspective.objectId.toString) + "/state"

    $http.put(getMethodUrl(url), req) onComplete {
      case Success(_) =>
        perspective.status = status
        p.success(Unit)
      case Failure(e) => p.failure(BackendException("Failed to update perspective status: " + e.getMessage))
    }
    p.future
  }

  /**
    * Remove perspective
    *
    * @param dictionary
    * @param perspective
    * @return
    */
  def removePerspective(dictionary: Dictionary, perspective: Perspective): Future[Unit] = {
    val p = Promise[Unit]()
    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" +
      encodeURIComponent(dictionary.objectId.toString) + "/perspective/" + encodeURIComponent(perspective.clientId
      .toString) +
      "/" + encodeURIComponent(perspective.objectId.toString)

    $http.delete(getMethodUrl(url)) onComplete {
      case Success(_) => p.success(())
      case Failure(e) => p.failure(BackendException("Failed to remove perspective: " + e.getMessage))
    }
    p.future
  }

  /**
    * Update perspective
    *
    * @param dictionary
    * @param perspective
    * @return
    */
  def updatePerspective(dictionary: Dictionary, perspective: Perspective): Future[Unit] = {
    val p = Promise[Unit]()
    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" +
      encodeURIComponent(dictionary.objectId.toString) + "/perspective/" + encodeURIComponent(perspective.clientId
      .toString) +
      "/" + encodeURIComponent(perspective.objectId.toString)
    $http.put(getMethodUrl(url), write(perspective)) onComplete {
      case Success(_) => p.success(())
      case Failure(e) => p.failure(BackendException("Failed to update perspective: " + e.getMessage))
    }
    p.future
  }


  /**
    * Get list of published perspectives for specified dictionary
    *
    * @param dictionary
    * @return
    */
  def getPublishedDictionaryPerspectives(dictionary: Dictionary): Future[Seq[Perspective]] = {
    val p = Promise[Seq[Perspective]]()
    getDictionaryPerspectives(dictionary) onComplete {
      case Success(perspectives) =>
        val publishedPerspectives = perspectives.filter(p => p.status.toUpperCase.equals("PUBLISHED"))
        p.success(publishedPerspectives)
      case Failure(e) => p.failure(BackendException("Failed to get published perspectives: " + e.getMessage))
    }
    p.future
  }

  def setPerspectiveMeta(dictionary: Dictionary, perspective: Perspective, metadata: MetaData) = {
    val p = Promise[Unit]()
    val url = ""
    $http.put(getMethodUrl(url), write(metadata)) onComplete {
      case Success(_) => p.success(())
      case Failure(e) => p.failure(BackendException("Failed to update perspective: " + e.getMessage))
    }
    p.future
  }

  /**
    * Get information about current user
    *
    * @return
    */
  def getCurrentUser: Future[User] = {
    val p = Promise[User]()
    $http.get[js.Object](getMethodUrl("user")) onComplete {
      case Success(js) =>
        try {
          val user = read[User](JSON.stringify(js))
          p.success(user)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed user json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed user data. Missing some " +
            "required fields: " + e.getMessage))
          case e: Throwable => p.failure(BackendException("Unknown exception:" + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get current user: " + e.getMessage))
    }
    p.future
  }

  /**
    * GetPerspective fields
    *
    * @param dictionary
    * @param perspective
    * @return
    */
  def getFields(dictionary: Dictionary, perspective: Perspective): Future[Seq[Field]] = {
    val p = Promise[Seq[Field]]()

    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" + encodeURIComponent(dictionary
      .objectId.toString) +
      "/perspective/" + encodeURIComponent(perspective.clientId.toString) + "/" + encodeURIComponent(perspective
      .objectId.toString) + "/fields"

    $http.get[js.Dynamic](getMethodUrl(url)) onComplete {
      case Success(response) =>
        try {
          val fields = read[Seq[Field]](js.JSON.stringify(response.fields))
          p.success(fields)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed fields json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed fields data. Missing some " +
            "required fields: " + e.getMessage))
          case e: Throwable => p.failure(BackendException("Unknown exception:" + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to fetch perspective fields: " + e.getMessage))
    }
    p.future
  }

  /**
    * Update perspective fields
    *
    * @param dictionary
    * @param perspective
    * @return
    */
  def updateFields(dictionary: Dictionary, perspective: Perspective): Future[Unit] = {
    val p = Promise[Unit]()
    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) + "/" + encodeURIComponent(dictionary
      .objectId.toString) + "/perspective/" + encodeURIComponent(perspective.clientId.toString) + "/" +
      encodeURIComponent(perspective
        .objectId.toString) + "/fields"
    $http.post(getMethodUrl(url), write(perspective)) onComplete {
      case Success(_) => p.success(())
      case Failure(e) => p.failure(BackendException("Failed to update perspective fields: " + e.getMessage))
    }
    p.future
  }


  /**
    * Get perspective with fields
    *
    * @param dictionary
    * @param perspective
    * @return
    */
  def getPerspectiveFields(dictionary: Dictionary, perspective: Perspective): Future[Perspective] = {
    val p = Promise[Perspective]()
    getFields(dictionary, perspective) onComplete {
      case Success(fields) =>
        perspective.fields = fields.toJSArray
        p.success(perspective)
      case Failure(e) => p.failure(BackendException("Failed to fetch perspective fields: " + e.getMessage))
    }
    p.future
  }


  /**
    *
    * @param dictionary
    * @param perspective
    * @return
    */
  def getPublishedLexicalEntriesCount(dictionary: Dictionary, perspective: Perspective): Future[Int] = {
    val p = Promise[Int]()

    val url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) +
      "/" + encodeURIComponent(dictionary.objectId.toString) +
      "/perspective/" + encodeURIComponent(perspective.clientId.toString) +
      "/" + encodeURIComponent(perspective.objectId.toString) + "/published_count"

    $http.get[js.Dynamic](getMethodUrl(url)) onComplete {
      case Success(response) =>
        try {
          p.success(response.count.asInstanceOf[Int])
        } catch {
          case e: Throwable => p.failure(BackendException("Unknown exception:" + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get published lexical entries count: " + e.getMessage))
    }
    p.future
  }


  /**
    * Get lexical entries list
    *
    * @param dictionary
    * @param perspective
    * @param action - "all", "published", etc
    * @param offset
    * @param count
    * @return
    */
  def getLexicalEntries(dictionary: Dictionary, perspective: Perspective, action: LexicalEntriesType, offset: Int, count: Int): Future[Seq[LexicalEntry]] = {
    val p = Promise[Seq[LexicalEntry]]()

    import LexicalEntriesType._
    val a = action match {
      case All => "all"
      case Published => "published"
    }

    var url = "dictionary/" + encodeURIComponent(dictionary.clientId.toString) +
      "/" + encodeURIComponent(dictionary.objectId.toString) +
      "/perspective/" + encodeURIComponent(perspective.clientId.toString) +
      "/" + encodeURIComponent(perspective.objectId.toString) + "/" + a

    url = addUrlParameter(url, "start_from", offset.toString)
    url = addUrlParameter(url, "count", count.toString)

    $http.get[js.Dynamic](getMethodUrl(url)) onComplete {
      case Success(response) =>
        try {
          val entries = read[Seq[LexicalEntry]](js.JSON.stringify(response.lexical_entries))
          p.success(entries)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed lexical entries json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed lexical entries data. Missing some required fields: " + e.getMessage))
          case e: Throwable => p.failure(BackendException("Unknown exception:" + e.getMessage))

        }
      case Failure(e) => p.failure(BackendException("Failed to get lexical entries: " + e.getMessage))
    }
    p.future
  }

  /**
    * Get list of dictionaries
    *
    * @param clientID client's id
    * @param objectID object's id
    *
    * @return sound markup in ELAN format
    */
  def getSoundMarkup(clientID: Int, objectID: Int): Future[String] = {
    val req = JSON.stringify(js.Dynamic.literal(client_id = clientID, object_id = objectID))
    val p = Promise[String]()

    $http.post[js.Dynamic](getMethodUrl("convert/markup"), req) onComplete {
      case Success(response) =>
        try {
          val markup = read[String](js.JSON.stringify(response.content))
          p.success(markup)
        } catch {
          case e: upickle.Invalid.Json => p.failure(BackendException("Malformed markup json:" + e.getMessage))
          case e: upickle.Invalid.Data => p.failure(BackendException("Malformed markup data. Missing some " +
            "required fields: " + e.getMessage))
        }
      case Failure(e) => p.failure(BackendException("Failed to get sound markup: " + e.getMessage))
    }
    p.future
  }

  /**
    * Log in
    *
    * @param username
    * @param password
    * @return
    */
  def login(username: String, password: String) = {
    val defer = $q.defer[Int]()
    val req = JSON.stringify(js.Dynamic.literal(login = username, password = password))
    $http.post[js.Dynamic](getMethodUrl("signin"), req) onComplete {
      case Success(response) =>
        try {
          val clientId = response.client_id.asInstanceOf[Int]
          defer.resolve(clientId)
        } catch {
          case e: Throwable => defer.reject("Unknown exception:" + e.getMessage)
        }
      case Failure(e) => defer.reject("Failed to sign in: " + e.getMessage)
    }
    defer.promise
  }

  /**
    * Logout user
    *
    * @return
    */
  def logout(): core.Promise[Unit] = {
    val defer = $q.defer[Unit]()
    val p = Promise[Unit]()
    $http.get[js.Dynamic](getMethodUrl("logout")) onComplete {
      case Success(response) => defer.resolve(())
      case Failure(e) => defer.reject(e.getMessage)
    }
    defer.promise
  }

  /**
    * Sign up
    * @param login
    * @param name
    * @param password
    * @param email
    * @param day
    * @param month
    * @param year
    * @return
    */
  def signup(login: String, name: String, password: String, email: String, day: String, month: String, year: String) = {
    val defer = $q.defer[Unit]()
    val req = JSON.stringify(js.Dynamic.literal(login = login, name = name, email = email, password = password, day = day, month = month, year = year))
    console.log(req)

    $http.post[js.Dynamic](getMethodUrl("signup"), req) onComplete {
      case Success(response) => defer.resolve(())
      case Failure(e) => defer.reject("Failed to sign up: " + e.getMessage)
    }
    defer.promise
  }
}


@injectable("BackendService")
class BackendServiceFactory($http: HttpService, $q: Q) extends Factory[BackendService] {
  override def apply(): BackendService = new BackendService($http, $q)
}
